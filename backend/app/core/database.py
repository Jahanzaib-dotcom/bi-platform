from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./biplatform.db",
)

# ---------------------------------------------------------------------------
# Auto-detect driver prefix for postgres vs sqlite
# ---------------------------------------------------------------------------

def _resolve_url(url: str) -> str:
    """Ensure the URL uses an async-compatible driver."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("sqlite:///") and not url.startswith("sqlite+aiosqlite"):
        return url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return url


_resolved_url = _resolve_url(DATABASE_URL)

from sqlalchemy import event

_connect_args: dict = {}
if "sqlite" in _resolved_url:
    _connect_args = {"check_same_thread": False, "timeout": 30.0}

engine: AsyncEngine = create_async_engine(
    _resolved_url,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
    connect_args=_connect_args,
)

if "sqlite" in _resolved_url:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=15000")
        except Exception:
            pass
        finally:
            cursor.close()

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session, rolling back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Lifecycle helpers
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all tables defined in the metadata, then add any missing columns (SQLite-safe)."""
    import app.models  # noqa: F401 – side-effect import

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we do it manually.
    if "sqlite" in _resolved_url:
        await _sqlite_add_missing_columns()


async def _sqlite_add_missing_columns() -> None:
    """Inspect the businesses table and ALTER TABLE to add any columns added to the model."""
    new_columns = [
        ("latitude", "REAL"),
        ("longitude", "REAL"),
        ("google_maps_url", "TEXT"),
        ("phone2", "VARCHAR(50)"),
        ("whatsapp", "VARCHAR(50)"),
        ("email2", "VARCHAR(255)"),
        ("contact_page_url", "TEXT"),
        ("about_page_url", "TEXT"),
        ("careers_page_url", "TEXT"),
        ("facebook_url", "TEXT"),
        ("instagram_url", "TEXT"),
        ("linkedin_url", "TEXT"),
        ("twitter_url", "TEXT"),
        ("tiktok_url", "TEXT"),
        ("youtube_url", "TEXT"),
        ("pinterest_url", "TEXT"),
        ("rating", "REAL"),
        ("review_count", "INTEGER"),
        ("opening_hours", "JSON"),
        ("services", "JSON"),
        ("founded_year", "INTEGER"),
        ("company_size", "VARCHAR(100)"),
        ("logo_url", "TEXT"),
        ("completeness_score", "REAL"),
        ("enrichment_data", "JSON"),
        ("last_enriched_at", "DATETIME"),
    ]
    import aiosqlite
    db_path = _resolved_url.replace("sqlite+aiosqlite:///", "").replace("sqlite+aiosqlite://", "")
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(businesses)") as cursor:
            existing = {row[1] async for row in cursor}
        for col_name, col_type in new_columns:
            if col_name not in existing:
                await db.execute(f"ALTER TABLE businesses ADD COLUMN {col_name} {col_type}")
        await db.commit()


async def close_db() -> None:
    """Dispose the engine connection pool."""
    await engine.dispose()
