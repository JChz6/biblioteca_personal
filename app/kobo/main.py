"""
Servicio de solo lectura para el navegador del Kobo (subdominio kobo.).

Corre como proceso/contenedor aparte de la app principal: no monta login,
subidas ni panel, así que esas rutas simplemente no existen en kobo.
El acceso se controla con un token secreto en la ruta (/k/<TOKEN>/).

Fase 0: solo una página de prueba con un EPUB, descargable por dos vías
(302 a URL firmada de GCS, o en streaming a través de este servidor).
"""
import hmac
import logging
import re
import time
import unicodedata
from collections import deque
from datetime import timedelta
from functools import lru_cache
from html import escape

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response, StreamingResponse
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.bigquery.catalogo import get_by_id, get_catalogo
from app.config import get_settings
from app.gcs.storage import get_storage_client, stream_blob


class KoboSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 32 bytes aleatorios como mínimo: 64 caracteres hex o 43 base64url.
    kobo_token: str = Field(min_length=43)
    kobo_signed_url_minutes: int = Field(default=15, ge=1, le=60)
    kobo_test_book_id: str = ""
    # Rate limit por IP: N respuestas 404 dentro de la ventana bloquean esa IP (429).
    kobo_max_failures: int = Field(default=20, ge=1)
    kobo_failure_window_seconds: int = Field(default=600, ge=10)


@lru_cache
def get_kobo_settings() -> KoboSettings:
    return KoboSettings()


CONTENT_TYPES = {
    ".epub": "application/epub+zip",
    ".kepub": "application/epub+zip",
    ".pdf": "application/pdf",
    ".cbz": "application/vnd.comicbook+zip",
}

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


def ascii_filename(libro: dict) -> str:
    """Nombre ASCII puro: el navegador del Kobo es viejo y no confiamos en filename*=UTF-8."""
    base = f"{libro.get('nuevo_titulo') or 'libro'} - {libro.get('autor') or ''}".strip(" -")
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    base = re.sub(r"[^A-Za-z0-9 .,()'_-]+", "", base)
    base = re.sub(r"\s+", " ", base).strip(" .") or "libro"
    return base[:120] + _extension(libro)


def _extension(libro: dict) -> str:
    return (libro.get("extension") or "").lower()


def _blob_path(uri_gcs: str) -> str:
    return uri_gcs.replace(f"gs://{get_settings().gcs_bucket}/", "", 1)


def _libro_descargable(book_id: str) -> dict | None:
    libro = get_by_id(book_id, incluir_privados=False)
    if libro is None or not libro.get("uri_gcs") or _extension(libro) not in CONTENT_TYPES:
        return None
    return libro


def _test_book() -> dict | None:
    book_id = get_kobo_settings().kobo_test_book_id
    if book_id:
        return _libro_descargable(book_id)
    epubs = [r for r in get_catalogo() if not r.get("privado") and r.get("uri_gcs") and _extension(r) == ".epub"]
    return min(epubs, key=lambda r: (r.get("nuevo_titulo") or "").lower(), default=None)


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<meta name="robots" content="noindex,nofollow">
<title>Mis libros</title>
<style>
body{{background:#fff;color:#000;font-family:serif;font-size:22px;margin:12px}}
h1{{font-size:26px;margin:0 0 12px}}
a.b{{display:block;border:2px solid #000;padding:16px;margin:0 0 16px;min-height:56px;color:#000;text-decoration:none;font-weight:bold}}
p{{margin:0 0 12px}}
small{{font-size:16px}}
</style></head><body>
{body}
</body></html>"""


@app.get("/robots.txt")
def robots() -> Response:
    return PlainTextResponse("User-agent: *\nDisallow: /\n")


@app.get("/k/{token}/")
def fase0(token: str, request: Request) -> Response:
    if not _token_ok(token):
        return _not_found()
    libro = _test_book()
    if libro is None:
        body = "<h1>Prueba Kobo</h1><p>No hay un EPUB de prueba disponible (revisa KOBO_TEST_BOOK_ID).</p>"
    else:
        titulo = escape(libro.get("nuevo_titulo") or "")
        autor = escape(libro.get("autor") or "")
        bid = escape(libro["id"])
        body = (
            "<h1>Prueba Kobo (Fase 0)</h1>"
            f"<p><b>{titulo}</b><br>{autor}</p>"
            f'<a class="b" href="d/{bid}">A. Descargar (directo desde Google)</a>'
            f'<a class="b" href="p/{bid}">B. Descargar (a través del servidor)</a>'
            f"<p><small>Navegador: {escape(request.headers.get('user-agent', '?'))}</small></p>"
        )
    return HTMLResponse(PAGE.format(body=body))


@app.get("/k/{token}/d/{book_id}")
def descargar_firmado(token: str, book_id: str) -> Response:
    if not _token_ok(token):
        return _not_found()
    libro = _libro_descargable(book_id)
    if libro is None:
        return _not_found()
    settings = get_settings()
    blob = get_storage_client().bucket(settings.gcs_bucket).blob(_blob_path(libro["uri_gcs"]))
    url = blob.generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=get_kobo_settings().kobo_signed_url_minutes),
        method="GET",
        response_disposition=f'attachment; filename="{ascii_filename(libro)}"',
        response_type=CONTENT_TYPES[_extension(libro)],
    )
    return RedirectResponse(url, status_code=302)


@app.get("/k/{token}/p/{book_id}")
def descargar_proxy(token: str, book_id: str) -> Response:
    """Plan B si el Kobo no logra descargar desde storage.googleapis.com (certificados, URL larga...)."""
    if not _token_ok(token):
        return _not_found()
    libro = _libro_descargable(book_id)
    if libro is None:
        return _not_found()
    settings = get_settings()
    blob = get_storage_client().bucket(settings.gcs_bucket).get_blob(_blob_path(libro["uri_gcs"]))
    if blob is None:
        return _not_found()
    headers = {"Content-Disposition": f'attachment; filename="{ascii_filename(libro)}"'}
    if blob.size is not None:
        headers["Content-Length"] = str(blob.size)
    return StreamingResponse(
        stream_blob(libro["uri_gcs"]), media_type=CONTENT_TYPES[_extension(libro)], headers=headers,
    )
