from functools import lru_cache

from google.oauth2 import service_account

from app.config import get_settings


@lru_cache
def get_credentials() -> service_account.Credentials:
    settings = get_settings()
    return service_account.Credentials.from_service_account_file(settings.google_application_credentials)
