"""Application configuration, loaded from environment (.env)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Core
    app_env: str = "local"
    app_secret_key: str = "change-me-dev-secret-key-min-32-chars-long"
    token_encryption_key: str = ""  # Fernet key; if empty a dev key is derived

    # Database
    database_url: str = "postgresql+psycopg://nq:nq@localhost:5432/nq"

    # Auth
    magic_link_ttl_minutes: int = 15
    session_ttl_hours: int = 168
    app_base_url: str = "http://localhost:8000"

    # LLM
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Reports
    default_gst_rate: float = 0.18

    # Shopify OAuth (authorization-code flow for merchant stores)
    shopify_api_key: str = ""      # app client_id
    shopify_api_secret: str = ""   # app client_secret
    shopify_scopes: str = "read_orders"
    shopify_redirect_uri: str = "" # defaults to {app_base_url}/api/integrations/shopify/callback

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
