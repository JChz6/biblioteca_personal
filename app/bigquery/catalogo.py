import time
import uuid
from functools import lru_cache
from typing import Any

import pandas as pd
from cachetools import TTLCache
from google.cloud import bigquery

from app.config import get_settings
from app.gcp_auth import get_credentials

_SCHEMA = [
    bigquery.SchemaField("id", "STRING"),
    bigquery.SchemaField("titulo_original", "STRING"),
    bigquery.SchemaField("autor", "STRING"),
    bigquery.SchemaField("nuevo_titulo", "STRING"),
    bigquery.SchemaField("extension", "STRING"),
    bigquery.SchemaField("categoria", "STRING"),
    bigquery.SchemaField("ruta_completa", "STRING"),
    bigquery.SchemaField("fecha_creacion", "DATETIME"),
    bigquery.SchemaField("fecha_modificacion", "DATETIME"),
    bigquery.SchemaField("comentarios", "STRING"),
    bigquery.SchemaField("ruta_local", "STRING"),
    bigquery.SchemaField("uri_gcs", "STRING"),
    bigquery.SchemaField("url_publica", "STRING"),
    bigquery.SchemaField("url_autenticada", "STRING"),
    bigquery.SchemaField("privado", "BOOLEAN"),
    bigquery.SchemaField("subido_por", "STRING"),
    bigquery.SchemaField("aprobado_por", "STRING"),
    bigquery.SchemaField("fecha_aprobacion", "DATETIME"),
]

_cache: TTLCache = TTLCache(maxsize=1, ttl=1)  # ttl real se fija en get_catalogo()


@lru_cache
def get_bq_client() -> bigquery.Client:
    settings = get_settings()
    return bigquery.Client(credentials=get_credentials(), project=settings.gcp_project_id)


def generar_id() -> str:
    return uuid.uuid4().hex[:12]


def _table_id() -> str:
    settings = get_settings()
    return f"{settings.gcp_project_id}.{settings.bq_dataset}.{settings.bq_table}"


def _fetch_all_from_bq() -> list[dict[str, Any]]:
    client = get_bq_client()
    rows = client.query(f"SELECT * FROM `{_table_id()}`").result()
    return [dict(r.items()) for r in rows]


def get_catalogo(force_refresh: bool = False) -> list[dict[str, Any]]:
    global _cache
    settings = get_settings()
    if _cache.ttl != settings.catalog_cache_ttl_seconds:
        _cache = TTLCache(maxsize=1, ttl=settings.catalog_cache_ttl_seconds)
    if force_refresh:
        _cache.pop("all", None)
    if "all" not in _cache:
        _cache["all"] = _fetch_all_from_bq()
    return _cache["all"]


def invalidate_cache() -> None:
    _cache.pop("all", None)


def listar_catalogo(
    search: str | None = None,
    categoria: str | None = None,
    incluir_privados: bool = False,
) -> list[dict[str, Any]]:
    rows = get_catalogo()
    if not incluir_privados:
        rows = [r for r in rows if not r.get("privado")]
    if categoria:
        rows = [r for r in rows if r.get("categoria") == categoria]
    if search:
        s = search.lower()
        rows = [
            r for r in rows
            if s in (r.get("nuevo_titulo") or "").lower() or s in (r.get("autor") or "").lower()
        ]
    return sorted(rows, key=lambda r: (r.get("nuevo_titulo") or "").lower())


def agrupar_por_obra(libros: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Agrupa filas que son el mismo libro en distintos formatos (ej. PDF + EPUB) —
    mismo (nuevo_titulo, autor) — en una sola entrada con varios "formatos"
    descargables, para que no se vean como duplicados en el catálogo.
    """
    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    orden: list[tuple[str, str]] = []
    for libro in libros:
        clave = (
            (libro.get("nuevo_titulo") or "").strip().lower(),
            (libro.get("autor") or "").strip().lower(),
        )
        if clave not in grupos:
            grupos[clave] = {
                "nuevo_titulo": libro.get("nuevo_titulo"),
                "autor": libro.get("autor"),
                "categoria": libro.get("categoria"),
                "privado": False,
                "formatos": [],
            }
            orden.append(clave)
        grupo = grupos[clave]
        grupo["privado"] = grupo["privado"] or bool(libro.get("privado"))
        grupo["formatos"].append({
            "id": libro["id"],
            "extension": (libro.get("extension") or "").lstrip("."),
        })

    resultado = [grupos[clave] for clave in orden]
    for grupo in resultado:
        grupo["formatos"].sort(key=lambda f: f["extension"])
    return resultado


def get_by_id(book_id: str, incluir_privados: bool = False) -> dict[str, Any] | None:
    for row in get_catalogo():
        if row.get("id") == book_id:
            if row.get("privado") and not incluir_privados:
                return None
            return row
    return None


def upsert_libro_aprobado(row: dict[str, Any]) -> None:
    """
    Sube una sola fila (libro recién aprobado) a una tabla temporal y hace MERGE
    con la tabla real, siguiendo el mismo patrón que incremental.py: carga a
    tabla temp (WRITE_TRUNCATE) -> MERGE por id -> borrar temp.
    """
    settings = get_settings()
    client = get_bq_client()

    df = pd.DataFrame([row])
    for col in ("fecha_creacion", "fecha_modificacion", "fecha_aprobacion"):
        df[col] = pd.to_datetime(df[col])
    df["privado"] = df["privado"].astype(bool)

    temp_table = f"{_table_id()}_temp_upsert_{int(time.time())}"
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        schema=_SCHEMA,
    )
    client.load_table_from_dataframe(df, temp_table, job_config=job_config).result()

    merge_sql = f"""
    MERGE `{_table_id()}` T
    USING `{temp_table}` S
    ON T.id = S.id
    WHEN MATCHED THEN
      UPDATE SET
        titulo_original = S.titulo_original,
        autor = S.autor,
        nuevo_titulo = S.nuevo_titulo,
        extension = S.extension,
        categoria = S.categoria,
        ruta_completa = S.ruta_completa,
        fecha_creacion = S.fecha_creacion,
        fecha_modificacion = S.fecha_modificacion,
        comentarios = S.comentarios,
        ruta_local = S.ruta_local,
        uri_gcs = S.uri_gcs,
        url_publica = S.url_publica,
        url_autenticada = S.url_autenticada,
        privado = S.privado,
        subido_por = S.subido_por,
        aprobado_por = S.aprobado_por,
        fecha_aprobacion = S.fecha_aprobacion,
        fecha_carga = CURRENT_DATETIME('America/Lima')
    WHEN NOT MATCHED THEN
      INSERT (
        id, titulo_original, autor, nuevo_titulo, extension, categoria, ruta_completa,
        fecha_creacion, fecha_modificacion, comentarios, ruta_local, uri_gcs, url_publica,
        url_autenticada, privado, subido_por, aprobado_por, fecha_aprobacion, fecha_carga
      )
      VALUES (
        S.id, S.titulo_original, S.autor, S.nuevo_titulo, S.extension, S.categoria, S.ruta_completa,
        S.fecha_creacion, S.fecha_modificacion, S.comentarios, S.ruta_local, S.uri_gcs, S.url_publica,
        S.url_autenticada, S.privado, S.subido_por, S.aprobado_por, S.fecha_aprobacion,
        CURRENT_DATETIME('America/Lima')
      )
    """
    client.query(merge_sql).result()
    client.delete_table(temp_table, not_found_ok=True)
    invalidate_cache()
