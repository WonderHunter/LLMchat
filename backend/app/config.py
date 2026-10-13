from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    secret_key: str = Field(min_length=32)
    fernet_key: str
    database_url: str = f"sqlite:///{(ROOT_DIR / 'backend' / 'llmchat.db').as_posix()}"
    allow_registration: bool = True
    session_days: int = 30
    cookie_secure: bool = False

    # Optionnelle : n'est envoyée que pour lire le catalogue OpenRouter, jamais pour le chat.
    openrouter_service_key: str | None = None
    catalog_refresh_minutes: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
