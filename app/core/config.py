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
    parser_provider: Literal[
        "deterministic",
        "structured_stub",
        "structured_model_shell",
        "openai_responses",
        "gemini_direct",
    ] = Field(
        default="deterministic",
        description="Internal parser provider selection; deterministic remains the safe default",
    )
    parser_shadow_enabled: bool = Field(
        default=True,
        description="Enable a non-authoritative shadow parser pass for comparison and observability",
    )
    parser_shadow_provider: Literal[
        "deterministic",
        "structured_stub",
        "structured_model_shell",
        "openai_responses",
        "gemini_direct",
    ] = Field(
        default="gemini_direct",
        description="Internal shadow parser provider selection; runs after authoritative parse/state work",
    )
    profile_provider: Literal[
        "deterministic",
        "gemini_direct",
    ] = Field(
        default="deterministic",
        description="Internal profiling provider selection; deterministic remains the safe default",
    )
    profile_shadow_enabled: bool = Field(
        default=True,
        description="Enable a non-authoritative shadow profile pass for comparison and observability",
    )
    profile_shadow_provider: Literal[
        "deterministic",
        "gemini_direct",
    ] = Field(
        default="gemini_direct",
        description="Internal shadow profile provider selection; runs after authoritative profile backfill",
    )
    structured_parser_validation_retries: int = Field(
        default=1,
        ge=0,
        le=3,
        description="Number of retry attempts for schema validation before falling back to deterministic parsing",
    )
    structured_parser_model_name: str = Field(
        default="unconfigured-structured-parser",
        description="Reserved model name for the future structured parser provider",
    )
    structured_parser_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description="Timeout budget in seconds for a future model-backed structured parser call",
    )
    structured_profile_model_name: str = Field(
        default="unconfigured-structured-profile",
        description="Reserved model name for the future structured profile provider",
    )
    structured_profile_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        le=300.0,
        description="Timeout budget in seconds for a future model-backed structured profile call",
    )
    push_delivery_enabled: bool = Field(
        default=True,
        description="Enable outbound push delivery after a push recommendation is generated",
    )
    push_delivery_channel: Literal["webhook_sink"] = Field(
        default="webhook_sink",
        description="Outbound push delivery channel; v1 only supports a single webhook sink",
    )
    push_webhook_url: str | None = Field(
        default=None,
        description="Webhook sink URL for real outbound push delivery",
    )
    push_webhook_timeout_seconds: float = Field(
        default=10.0,
        gt=0.0,
        le=120.0,
        description="Timeout budget in seconds for outbound push webhook delivery",
    )
    push_delivery_max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum outbound push delivery attempts before marking a push as failed",
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
    openai_api_key: str | None = Field(default=None, description="Optional OpenAI API key for structured parser calls")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="Base URL for OpenAI Responses API-compatible structured parser calls",
    )
    gemini_api_key: str | None = Field(
        default=None,
        description="Optional Gemini Developer API key for AI Studio-backed structured parser calls",
    )
    gemini_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        description="Base URL for Gemini Developer API generateContent calls",
    )

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
