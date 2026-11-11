"""
Servicio de solo lectura para el navegador del Kobo (subdominio kobo.).

Corre como proceso/contenedor aparte de la app principal: no monta login,
subidas ni panel, así que esas rutas simplemente no existen en kobo.
El acceso se controla con un token secreto en la ruta (/k/<TOKEN>/).

Rutas:
  GET /k/<TOKEN>/            lista paginada (?p=2, ?l=A, ?q=texto), más recientes primero
  GET /k/<TOKEN>/d/<id>      302 a una URL firmada V4 de GCS, o streaming si KOBO_DOWNLOAD_MODE=proxy
  GET /robots.txt            bloquea todo
  todo lo demás              404 genérico
"""
import hmac
import logging
import math
import re
import time
import unicodedata
from collections import deque
from datetime import timedelta
from functools import lru_cache
from html import escape
from typing import Any, Literal
from urllib.parse import urlencode

from cachetools import TTLCache
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.bigquery.catalogo import agrupar_por_obra, get_by_id, get_catalogo, listar_catalogo, ordenar_grupos
from app.config import get_settings
from app.gcs.storage import get_storage_client, stream_blob
from app.text_utils import alphabetical_key, initial_letter

log = logging.getLogger(__name__)


class KoboSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 32 bytes aleatorios como mínimo: 64 caracteres hex o 43 base64url.
    kobo_token: str = Field(min_length=43)
    kobo_signed_url_minutes: int = Field(default=15, ge=1, le=60)
    # redirect: 302 a URL firmada de GCS (no pasa por el homelab).
    # proxy: el archivo pasa por este servicio y Cloudflare (por si el Kobo descarga mal desde Google).
    kobo_download_mode: Literal["redirect", "proxy"] = "redirect"
    kobo_page_size: int = Field(default=20, ge=5, le=50)
    # Rate limit por IP: N respuestas 404 dentro de la ventana bloquean esa IP (429).
    kobo_max_failures: int = Field(default=20, ge=1)
    kobo_failure_window_seconds: int = Field(default=600, ge=10)
    kobo_sizes_cache_seconds: int = Field(default=300, ge=0)


@lru_cache
def get_kobo_settings() -> KoboSettings:
    return KoboSettings()


# Orden = prioridad del botón dentro de cada obra (EPUB primero).
CONTENT_TYPES = {
    ".epub": "application/epub+zip",
    ".kepub": "application/epub+zip",
    ".pdf": "application/pdf",
    ".cbz": "application/vnd.comicbook+zip",
    ".cbr": "application/vnd.comicbook-rar",
    ".mobi": "application/x-mobipocket-ebook",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
}
_FORMAT_RANK = {ext.lstrip("."): i for i, ext in enumerate(CONTENT_TYPES)}

SECURITY_HEADERS = {
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}


# --- Logs: nunca registrar el token -----------------------------------------

_TOKEN_IN_PATH = re.compile(r"/k/[^/?\s]+")


def mask_token(text: str) -> str:
    return _TOKEN_IN_PATH.sub("/k/***", text)


class _MaskTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(mask_token(a) if isinstance(a, str) else a for a in record.args)
        elif isinstance(record.msg, str):
            record.msg = mask_token(record.msg)
        return True


for _name in ("uvicorn.access", "uvicorn.error"):
    logging.getLogger(_name).addFilter(_MaskTokenFilter())


# --- Rate limit en memoria (un solo proceso) --------------------------------

_failures: dict[str, deque] = {}


def _client_ip(request: Request) -> str:
    # El contenedor solo es alcanzable vía Cloudflare Tunnel, así que este header es fiable.
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


def _is_blocked(ip: str, now: float) -> bool:
    settings = get_kobo_settings()
    q = _failures.get(ip)
    if not q:
        return False
    while q and now - q[0] > settings.kobo_failure_window_seconds:
        q.popleft()
    if not q:
        _failures.pop(ip, None)
        return False
    return len(q) >= settings.kobo_max_failures


def _record_failure(ip: str, now: float) -> None:
    if len(_failures) > 10_000:  # evita crecer sin límite ante un barrido desde muchas IPs
        _failures.clear()
    _failures.setdefault(ip, deque()).append(now)


# --- App -------------------------------------------------------------------

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.router.redirect_slashes = False  # /k/<lo-que-sea> sin barra no debe redirigir: daría pistas


def _not_found() -> Response:
    return PlainTextResponse("Not Found", status_code=404)


@app.exception_handler(404)
async def _handle_404(request: Request, exc) -> Response:
    return _not_found()


@app.exception_handler(405)
async def _handle_405(request: Request, exc) -> Response:
    return _not_found()


@app.middleware("http")
async def _guard(request: Request, call_next):
    ip = _client_ip(request)
    now = time.monotonic()
    if _is_blocked(ip, now):
        response: Response = PlainTextResponse("Too Many Requests", status_code=429)
    elif request.method not in ("GET", "HEAD"):
        response = _not_found()  # solo lectura
    else:
        response = await call_next(request)
    if response.status_code == 404:
        _record_failure(ip, now)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


def _token_ok(token: str) -> bool:
    expected = get_kobo_settings().kobo_token.encode()
    return hmac.compare_digest(token.encode(), expected)


# --- Datos -----------------------------------------------------------------

def _extension(libro: dict) -> str:
    return (libro.get("extension") or "").lower()


def _blob_path(uri_gcs: str) -> str:
    return uri_gcs.replace(f"gs://{get_settings().gcs_bucket}/", "", 1)


def ascii_filename(libro: dict) -> str:
    """Nombre ASCII puro: el navegador del Kobo es viejo y no confiamos en filename*=UTF-8."""
    base = f"{libro.get('nuevo_titulo') or 'libro'} - {libro.get('autor') or ''}".strip(" -")
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9 .,()'_-]+", "", base)
    base = re.sub(r"\s+", " ", base).strip(" .") or "libro"
    return base[:120] + _extension(libro)


_sizes: TTLCache = TTLCache(maxsize=1, ttl=1)


def _blob_sizes() -> dict[str, int]:
    """Tamaño de cada blob del bucket (el catálogo no lo guarda). Un solo listado, cacheado."""
    global _sizes
    ttl = get_kobo_settings().kobo_sizes_cache_seconds
    if _sizes.ttl != ttl:
        _sizes = TTLCache(maxsize=1, ttl=max(ttl, 1))
    if "all" not in _sizes:
        try:
            bucket = get_settings().gcs_bucket
            _sizes["all"] = {b.name: b.size for b in get_storage_client().list_blobs(bucket) if b.size is not None}
        except Exception:
            log.exception("No se pudo listar el bucket; la lista se muestra sin tamaños")
            return {}
    return _sizes["all"]


def _human_size(n: int | None) -> str:
    if n is None:
        return ""
    if n < 1_000_000:
        return f"{max(1, round(n / 1000))} KB"
    return f"{n / 1_000_000:.1f} MB".replace(".", ",")


def _fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    return "".join(c for c in s if not unicodedata.combining(c))


def _obras(q: str) -> list[dict[str, Any]]:
    """Obras con al menos un formato legible en el Kobo, más recientes primero (igual que "Recientes" en la web)."""
    rows = listar_catalogo(incluir_privados=True)
    rows = [r for r in rows if r.get("uri_gcs") and _extension(r) in CONTENT_TYPES]
    if q:
        # Sin acentos ni mayúsculas: escribir "á" en el teclado del Kobo es lento.
        needle = _fold(q)
        rows = [r for r in rows if needle in _fold(r.get("nuevo_titulo")) or needle in _fold(r.get("autor"))]
    grupos = ordenar_grupos(agrupar_por_obra(rows), "fecha")
    for g in grupos:
        g["formatos"].sort(key=lambda f: _FORMAT_RANK.get(f["extension"].lower(), 99))
    return grupos


def _libro_descargable(book_id: str) -> dict | None:
    libro = get_by_id(book_id, incluir_privados=True)
    if libro is None or not libro.get("uri_gcs") or _extension(libro) not in CONTENT_TYPES:
        return None
    return libro


# --- HTML ------------------------------------------------------------------

PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<meta name="robots" content="noindex,nofollow">
<title>Mis libros</title>
<style>
body{{background:#fff;color:#000;font-family:serif;font-size:22px;line-height:1.3;margin:10px}}
a{{color:#000}}
h1{{font-size:26px;margin:0 0 8px}}
.ix a{{display:inline-block;min-width:44px;padding:10px 0;text-align:center;font-size:22px;text-decoration:none;border:1px solid #000;margin:0 2px 4px 0}}
.ix a.on{{background:#000;color:#fff}}
form{{margin:8px 0}}
input{{font-size:22px;padding:8px;border:2px solid #000;width:60%}}
button{{font-size:22px;padding:8px 14px;border:2px solid #000;background:#fff}}
.r{{border-top:2px solid #000;padding:10px 0;min-height:56px}}
.t{{font-weight:bold;font-size:23px}}
.a{{font-size:20px}}
.f a{{display:inline-block;min-height:30px;padding:12px 14px;margin:6px 8px 0 0;border:2px solid #000;text-decoration:none;font-size:20px;font-weight:bold}}
.nav{{border-top:2px solid #000;padding:12px 0;font-size:22px}}
.nav a{{display:inline-block;padding:14px 18px;border:2px solid #000;text-decoration:none;font-weight:bold}}
.nav span{{padding:0 10px}}
</style></head><body>
{body}
</body></html>"""


def _qs(**params) -> str:
    clean = {k: v for k, v in params.items() if v not in (None, "", 1)}
    return "?" + urlencode(clean) if clean else "./"


def _parse_page(raw: str | None) -> int:
    try:
        return max(1, int(raw or 1))
    except ValueError:
        return 1


def render_lista(grupos_todos: list[dict], letra: str, q: str, page: int) -> str:
    size = get_kobo_settings().kobo_page_size
    sizes = _blob_sizes()
    por_id = {r["id"]: r for r in get_catalogo()}

    letras_con_libros = {initial_letter(g.get("nuevo_titulo") or "") for g in grupos_todos}
    grupos = [g for g in grupos_todos if initial_letter(g.get("nuevo_titulo") or "") == letra] if letra else grupos_todos

    total = len(grupos)
    pages = max(1, math.ceil(total / size))
    page = min(page, pages)
    visibles = grupos[(page - 1) * size: page * size]

    out = [f"<h1>Mis libros <small>({total})</small></h1>"]

    letras = sorted(letras_con_libros, key=lambda x: (x == "#", alphabetical_key(x)))
    ix = [f'<a href="./"{" class=on" if not letra else ""}>Todos</a>']
    for x in letras:
        cls = ' class="on"' if x == letra else ""
        ix.append(f'<a href="{escape(_qs(l=x))}"{cls}>{escape(x)}</a>')
    out.append('<div class="ix">' + "".join(ix) + "</div>")
    out.append(f'<form method="get" action="./"><input name="q" value="{escape(q)}">'
               f' <button type="submit">Buscar</button></form>')

    if not visibles:
        out.append('<p class="r">No hay libros.</p>')
    for g in visibles:
        botones = []
        for f in g["formatos"]:
            fila = por_id.get(f["id"], {})
            tam = _human_size(sizes.get(_blob_path(fila.get("uri_gcs") or "")))
            etiqueta = f["extension"].upper() + (f" &middot; {tam}" if tam else "")
            botones.append(f'<a href="d/{escape(f["id"])}">Descargar {etiqueta}</a>')
        out.append(
            f'<div class="r"><div class="t">{escape(g.get("nuevo_titulo") or "")}</div>'
            f'<div class="a">{escape(g.get("autor") or "")}</div>'
            f'<div class="f">{"".join(botones)}</div></div>'
        )

    nav = []
    if page > 1:
        nav.append(f'<a href="{escape(_qs(l=letra, q=q, p=page - 1))}">&laquo; Anterior</a>')
    nav.append(f"<span>{page} / {pages}</span>")
    if page < pages:
        nav.append(f'<a href="{escape(_qs(l=letra, q=q, p=page + 1))}">Siguiente &raquo;</a>')
    out.append('<div class="nav">' + "".join(nav) + "</div>")
    return PAGE.format(body="\n".join(out))


# --- Rutas -----------------------------------------------------------------

@app.get("/robots.txt")
def robots() -> Response:
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.get("/k/{token}/")
def lista(token: str, request: Request) -> Response:
    if not _token_ok(token):
        return _not_found()
    params = request.query_params
    q = (params.get("q") or "").strip()[:100]
    letra = (params.get("l") or "").strip().upper()[:1]
    return HTMLResponse(render_lista(_obras(q), letra, q, _parse_page(params.get("p"))))


@app.get("/k/{token}/d/{book_id}")
def descargar(token: str, book_id: str) -> Response:
    if not _token_ok(token):
        return _not_found()
    libro = _libro_descargable(book_id)
    if libro is None:
        return _not_found()
    bucket = get_storage_client().bucket(get_settings().gcs_bucket)
    content_type = CONTENT_TYPES[_extension(libro)]
    disposition = f'attachment; filename="{ascii_filename(libro)}"'
    if get_kobo_settings().kobo_download_mode == "proxy":
        blob = bucket.get_blob(_blob_path(libro["uri_gcs"]))
        if blob is None:
            return _not_found()
        headers = {"Content-Disposition": disposition}
        if blob.size is not None:
            headers["Content-Length"] = str(blob.size)
        return StreamingResponse(stream_blob(libro["uri_gcs"]), media_type=content_type, headers=headers)
    blob = bucket.blob(_blob_path(libro["uri_gcs"]))
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=get_kobo_settings().kobo_signed_url_minutes),
        method="GET",
        response_disposition=disposition,
        response_type=content_type,
    )
    return RedirectResponse(url, status_code=302)
