"""Application configuration using Pydantic settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = PROJECT_ROOT / ".env"


class AppSettings(BaseSettings):
    """Core application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    env: Literal["local", "dev", "prod"] = Field(default="local", description="Runtime environment")
    debug: bool = Field(default=True, description="Enable debug features")

    app_name: str = Field(default="Dynamic Life Navigator", description="Application name")
    app_version: str = Field(default="0.1.0", description="Application version")
    api_prefix: str = Field(default="/api/v1", description="Base prefix for public HTTP APIs")
    log_level: str = Field(default="INFO", description="Application log level")
    default_user_id: str = Field(default="local-user", description="Default single-user identifier for MVP mode")
    enable_worker_dispatch: bool = Field(
        default=False,
        description="Enable actual Celery task dispatch from request handlers",
    )

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/dln",
        description="SQLAlchemy database URL for PostgreSQL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for cache/idempotency and as Celery broker",
    )
    webhook_idempotency_ttl_seconds: int = Field(
        default=86400,
        description="TTL in seconds for Redis-backed webhook duplicate suppression",
    )
    celery_broker_url: str | None = Field(
        default=None,
        description="Celery broker URL; defaults to redis_url if not set",
    )
    celery_result_backend: str | None = Field(
        default=None,
        description="Celery result backend; defaults to redis_url if not set",
    )

    sentry_dsn: str | None = Field(default=None, description="Optional Sentry DSN")

    @property
    def effective_celery_broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached AppSettings instance."""

    return AppSettings()
