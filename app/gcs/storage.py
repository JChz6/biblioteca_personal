from collections.abc import Generator
from functools import lru_cache

from google.api_core.exceptions import NotFound
from google.cloud import storage

from app.config import get_settings
from app.gcp_auth import get_credentials

_UNSAFE_CHARS = ['/', '\\', ':', '*', '?', '¿', '"', '<', '>', '|']


@lru_cache
def get_storage_client() -> storage.Client:
    settings = get_settings()
    return storage.Client(credentials=get_credentials(), project=settings.gcp_project_id)


def safe_filename(s: str) -> str:
    s = str(s or "").strip()
    for c in _UNSAFE_CHARS:
        s = s.replace(c, "")
    return s.replace("\n", " ").replace("\r", "")


def upload_to_gcs(local_path: str, dest_path: str) -> str:
    settings = get_settings()
    bucket = get_storage_client().bucket(settings.gcs_bucket)
    blob = bucket.blob(dest_path)
    blob.upload_from_filename(local_path)
    return f"gs://{settings.gcs_bucket}/{dest_path}"


def construir_urls_gcs(gcs_uri: str) -> tuple[str, str]:
    settings = get_settings()
    if not gcs_uri:
        return "", ""
    blob_path = gcs_uri.replace(f"gs://{settings.gcs_bucket}/", "")
    url_publica = f"https://storage.googleapis.com/{settings.gcs_bucket}/{blob_path}"
    url_autenticada = f"https://storage.cloud.google.com/{settings.gcs_bucket}/{blob_path}"
    return url_publica, url_autenticada


def delete_blob(gcs_uri: str) -> None:
    settings = get_settings()
    blob_path = gcs_uri.replace(f"gs://{settings.gcs_bucket}/", "")
    bucket = get_storage_client().bucket(settings.gcs_bucket)
    try:
        bucket.blob(blob_path).delete()
    except NotFound:
        pass


def stream_blob(gcs_uri: str, chunk_size: int = 1024 * 1024) -> Generator[bytes, None, None]:
    """Descarga un blob de GCS en chunks, para servirlo via StreamingResponse sin exponer la URL de GCS."""
    settings = get_settings()
    blob_path = gcs_uri.replace(f"gs://{settings.gcs_bucket}/", "")
    bucket = get_storage_client().bucket(settings.gcs_bucket)
    blob = bucket.blob(blob_path)
    with blob.open("rb", chunk_size=chunk_size) as f:
        while chunk := f.read(chunk_size):
            yield chunk
