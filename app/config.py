from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    owner_email: str
    google_client_id: str
    google_client_secret: str
    session_secret_key: str
    base_url: str = "http://localhost:8000"

    gcp_project_id: str = "big-query-406221"
    bq_dataset: str = "biblioteca_personal"
    bq_table: str = "catalogo"
    gcs_bucket: str = "biblioteca_personal"
    google_application_credentials: str = "./service_account.json"

    database_url: str = "sqlite:///./data/app.db"
    pending_dir: str = "./data/pending"

    # El catálogo se invalida explícitamente al aprobar un libro (ver invalidate_cache()),
    # así que este TTL es solo una red de seguridad — puede ser largo sin afectar frescura.
    catalog_cache_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()
