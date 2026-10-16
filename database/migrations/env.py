"""
Alembic env.py — async migrations with asyncpg, supports both online and
offline modes, and auto-generates migrations from all registered ORM models.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ---------------------------------------------------------------------------
# Make the backend package importable when running alembic from the
# database/migrations/ directory.
# ---------------------------------------------------------------------------
BACKEND_ROOT = Path(__file__).resolve().parents[2] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# ---------------------------------------------------------------------------
# Register ALL ORM models so their tables appear in target_metadata.
# The import below is a side-effect import — it populates Base.metadata.
# ---------------------------------------------------------------------------
import app.models  # noqa: F401, E402 – side-effect: registers all table mappings

from app.core.database import Base  # noqa: E402

# ---------------------------------------------------------------------------
# Alembic Config object (from alembic.ini, if present).
# ---------------------------------------------------------------------------
config = context.config

# Interpret the config file's logging section, if it exists.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Resolve the database URL.
# Priority: env var DATABASE_URL > alembic.ini sqlalchemy.url > default sqlite
# ---------------------------------------------------------------------------

def _get_sync_url() -> str:
    """
    Return a *synchronous* database URL suitable for Alembic's engine.

    We derive it from DATABASE_URL (which may use an async driver) and
    strip the async driver suffix so Alembic can use a standard sync driver.
    """
    url = os.getenv("DATABASE_URL", "")

    if not url:
        # Fall back to the value set in alembic.ini (may be empty / placeholder).
        url = config.get_main_option("sqlalchemy.url", "")

    if not url:
        # Last resort: local SQLite file next to the backend directory.
        url = "sqlite:///./biplatform.db"

    # Ensure async driver variants are replaced with sync equivalents.
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    url = url.replace("postgres+asyncpg://", "postgresql://")
    url = url.replace("sqlite+aiosqlite:///", "sqlite:///")

    return url


def _get_async_url() -> str:
    """
    Return an *asynchronous* database URL for the online async runner.
    """
    url = os.getenv("DATABASE_URL", "")

    if not url:
        url = config.get_main_option("sqlalchemy.url", "")

    if not url:
        url = "sqlite+aiosqlite:///./biplatform.db"

    # Ensure the correct async driver is present.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("sqlite:///") and "+aiosqlite" not in url:
        url = url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

    return url


# ---------------------------------------------------------------------------
# Target metadata — Alembic compares this against the live schema to
# generate "upgrade" / "downgrade" migration scripts automatically.
# ---------------------------------------------------------------------------
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode — emit SQL to stdout without connecting
    to the database.  Useful for reviewing or applying migrations manually.
    """
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode (async)
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    """Execute migrations using an already-open synchronous *connection*."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        # Let Alembic manage the transaction for each migration step.
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create an async engine from the resolved URL and drive migrations through
    a synchronous connection proxy so that Alembic's context manager works.
    """
    async_url = _get_async_url()

    # Build a minimal config dict for async_engine_from_config.
    configuration = {
        "sqlalchemy.url": async_url,
    }

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode — runs the async coroutine."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
