"""
Application configuration using Pydantic settings.

Phase 0:
- Provides a single source of truth for environment-based configuration.
- Later phases can extend this without changing call sites.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings


class AppSettings(BaseSettings):
    """Core application settings loaded from environment variables."""

    env: Literal["local", "dev", "prod"] = Field(default="local", description="Runtime environment")
    debug: bool = Field(default=True, description="Enable debug features")

    # Database and cache
    database_url: AnyUrl = Field(
        default="postgresql+psycopg2://user:password@localhost:5432/dln",
        description="SQLAlchemy database URL for PostgreSQL",
    )
    redis_url: AnyUrl = Field(
        default="redis://localhost:6379/0",
        description="Redis URL for cache/idempotency and as Celery broker",
    )

    # Celery
    celery_broker_url: Optional[AnyUrl] = Field(
        default=None,
        description="Celery broker URL; defaults to redis_url if not set",
    )
    celery_result_backend: Optional[AnyUrl] = Field(
        default=None,
        description="Celery result backend; defaults to redis_url if not set",
    )

    # API
    api_prefix: str = Field(default="/api/v1", description="Base prefix for public HTTP APIs")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def effective_celery_broker_url(self) -> str:
        return str(self.celery_broker_url or self.redis_url)

    @property
    def effective_celery_result_backend(self) -> str:
        return str(self.celery_result_backend or self.redis_url)


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return a cached AppSettings instance."""

    return AppSettings()  # type: ignore[arg-type]

