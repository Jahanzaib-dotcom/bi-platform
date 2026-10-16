"""
Application configuration using pydantic-settings.
Reads from environment variables and .env files.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    APP_NAME: str = "BI-Platform"
    APP_ENV: str = Field(default="development", pattern="^(development|staging|production)$")
    APP_PORT: int = 8000
    APP_SECRET_KEY: str = "change-me-in-production"
    DEBUG: bool = True

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    # Async URL (postgres or sqlite).  Used by SQLAlchemy async engine.
    DATABASE_URL: str = "sqlite+aiosqlite:///./biplatform.db"
    # Sync URL used by Alembic migrations (postgres only; auto-derived for sqlite)
    DATABASE_URL_SYNC: str = ""
    SQLITE_URL: str = "sqlite+aiosqlite:///./biplatform.db"

    # Connection pool settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE_SECONDS: int = 3600

    # ------------------------------------------------------------------ #
    # Redis
    # ------------------------------------------------------------------ #
    REDIS_URL: str = "redis://localhost:6379/0"

    # ------------------------------------------------------------------ #
    # Authentication / JWT
    # ------------------------------------------------------------------ #
    JWT_SECRET_KEY: str = "change-jwt-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # ------------------------------------------------------------------ #
    # AI / Claude
    # ------------------------------------------------------------------ #
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL: str = "claude-opus-4-8"
    GEMINI_API_KEY: str = ""

    # ------------------------------------------------------------------ #
    # External search providers (optional)
    # ------------------------------------------------------------------ #
    SERPAPI_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    GOOGLE_PLACES_API_KEY: str = ""
    YELP_API_KEY: str = ""

    # ------------------------------------------------------------------ #
    # Discovery flags
    # ------------------------------------------------------------------ #
    # DuckDuckGo is enrichment-only and off by default
    DDGS_ENRICHMENT_ENABLED: bool = False
    # WhatsApp Business API registration check (paid) — off by default
    VERIFY_WHATSAPP_REGISTRATION: bool = False

    # ------------------------------------------------------------------ #
    # Outreach email provider
    # ------------------------------------------------------------------ #
    # smtp  = manual single sends via Gmail SMTP (existing)
    # brevo = bulk cold outreach via Brevo free tier (300/day)
    OUTREACH_EMAIL_PROVIDER: str = "smtp"
    BREVO_API_KEY: str = ""

    # ------------------------------------------------------------------ #
    # Playwright / scraping
    # ------------------------------------------------------------------ #
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT: int = 30000  # milliseconds
    SCREENSHOT_DIR: str = "./storage/screenshots"

    # ------------------------------------------------------------------ #
    # Celery
    # ------------------------------------------------------------------ #
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_SERIALIZER: str = "json"
    CELERY_RESULT_SERIALIZER: str = "json"
    CELERY_ACCEPT_CONTENT: list[str] = ["json"]
    CELERY_TIMEZONE: str = "UTC"

    # ------------------------------------------------------------------ #
    # Email / SMTP
    # ------------------------------------------------------------------ #
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_NAME: str = "Web Services Team"
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    # ------------------------------------------------------------------ #
    # Rate limiting
    # ------------------------------------------------------------------ #
    DEFAULT_RATE_LIMIT_REQUESTS: int = 10
    DEFAULT_RATE_LIMIT_PERIOD: int = 60  # seconds

    # ------------------------------------------------------------------ #
    # Export / storage
    # ------------------------------------------------------------------ #
    EXPORT_DIR: str = "./storage/exports"
    STORAGE_BASE_DIR: str = "./storage"

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://192.168.18.116:3000",
        "http://192.168.18.116:3001",
        "http://192.168.18.116:3002",
        "http://192.168.18.116:3003",
    ]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: list[str] = ["*"]
    CORS_ALLOW_HEADERS: list[str] = ["*"]

    # ------------------------------------------------------------------ #
    # Frontend URLs
    # ------------------------------------------------------------------ #
    NEXT_PUBLIC_API_URL: str = "http://localhost:8000"
    NEXT_PUBLIC_WS_URL: str = "ws://localhost:8000"

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #

    @field_validator("APP_SECRET_KEY", "JWT_SECRET_KEY", mode="before")
    @classmethod
    def _warn_insecure_secrets(cls, v: str) -> str:
        insecure = {
            "change-me-in-production",
            "change-jwt-secret-in-production",
            "your-super-secret-key-change-in-production",
            "your-jwt-secret-change-in-production",
        }
        if v in insecure:
            import warnings
            warnings.warn(
                "Insecure default secret key detected. "
                "Set a strong random value before deploying to production.",
                stacklevel=2,
            )
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: Any) -> list[str]:
        """Accept comma-separated string or a JSON list from the environment."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def _resolve_database_urls(self) -> "Settings":
        """
        When DATABASE_URL is not explicitly overridden to postgres, fall back
        to SQLITE_URL so the app works out-of-the-box without postgres.
        The sync URL is derived automatically for SQLite migrations.
        """
        db_url = self.DATABASE_URL

        # If the caller left DATABASE_URL as a postgres URL (non-sqlite) we
        # leave it alone; otherwise use the sqlite URL.
        if not db_url.startswith("postgresql"):
            object.__setattr__(self, "DATABASE_URL", self.SQLITE_URL)

        # Derive the sync URL when not explicitly set.
        if not self.DATABASE_URL_SYNC:
            sync_url = self.DATABASE_URL
            # Convert async drivers to sync equivalents for Alembic.
            sync_url = sync_url.replace("+asyncpg", "").replace("+aiosqlite", "")
            object.__setattr__(self, "DATABASE_URL_SYNC", sync_url)

        return self

    # ------------------------------------------------------------------ #
    # Computed properties
    # ------------------------------------------------------------------ #

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def screenshot_path(self) -> Path:
        p = Path(self.SCREENSHOT_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def export_path(self) -> Path:
        p = Path(self.EXPORT_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def storage_path(self) -> Path:
        p = Path(self.STORAGE_BASE_DIR)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def using_postgres(self) -> bool:
        return self.DATABASE_URL.startswith("postgresql")

    @property
    def using_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """
    Return the (cached) Settings singleton.

    The first call reads from environment variables / .env; subsequent calls
    return the cached instance.  In tests, call ``load_settings.cache_clear()``
    before patching environment variables to force a fresh load.
    """
    return Settings()


# Module-level singleton for convenient import across the codebase.
settings: Settings = load_settings()
