"""
Shared pytest fixtures for the BI-Platform backend test suite.

All fixtures use SQLite in-memory so no external DB is needed.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Override DATABASE_URL before any app import so aiosqlite is used in tests
# ---------------------------------------------------------------------------
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SQLITE_URL", "sqlite+aiosqlite:///:memory:")

# ---------------------------------------------------------------------------
# App & ORM imports (after env override)
# ---------------------------------------------------------------------------
from app.core.database import Base, get_db  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.models.audit import AuditReport, AuditStatus  # noqa: E402
from app.models.business import Business  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.discovery_job import DiscoveryJob, JobStatus  # noqa: E402


# ---------------------------------------------------------------------------
# pytest-asyncio configuration
# ---------------------------------------------------------------------------

pytest_plugins = ["pytest_asyncio"]


# ---------------------------------------------------------------------------
# In-memory SQLite engine & session factory
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a fresh in-memory SQLite engine for every test function."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    # Import all models so their metadata is registered before create_all
    import app.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session bound to the in-memory engine."""
    factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def test_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Return an AsyncClient wired to the FastAPI app.

    The database dependency ``get_db`` is overridden to return the test
    session so every request operates on the in-memory SQLite database.
    """
    from app.main import create_app

    app: FastAPI = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield async_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def sample_user(async_session: AsyncSession) -> User:
    """Persist a single active user and return it."""
    user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        username="testuser",
        hashed_password=get_password_hash("Password123!"),
        full_name="Test User",
        is_active=True,
        is_superuser=False,
        api_key=secrets.token_urlsafe(48),
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def sample_business(async_session: AsyncSession) -> Business:
    """Persist a sample business record and return it."""
    business = Business(
        id=uuid.uuid4(),
        name="Acme Plumbing Co.",
        slug="acme-plumbing-co-test",
        description="Local plumbing services",
        industry="plumbing",
        category="trades",
        country="US",
        state="TX",
        city="Austin",
        phone="+15125550101",
        email="contact@acmeplumbing.example",
        website_url="https://acmeplumbing.example",
        has_website=True,
        source="manual",
        overall_score=42.5,
        opportunity_score=67.0,
        revenue_potential=8500.0,
        audit_count=0,
        discovered_at=datetime.now(timezone.utc),
    )
    async_session.add(business)
    await async_session.commit()
    await async_session.refresh(business)
    return business


@pytest_asyncio.fixture(scope="function")
async def sample_audit(
    async_session: AsyncSession, sample_business: Business
) -> AuditReport:
    """Persist a completed audit report linked to *sample_business*."""
    audit = AuditReport(
        id=uuid.uuid4(),
        business_id=sample_business.id,
        status=AuditStatus.completed,
        website_url="https://acmeplumbing.example",
        ui_score=45.0,
        ux_score=40.0,
        mobile_score=35.0,
        seo_score=30.0,
        accessibility_score=55.0,
        speed_score=50.0,
        security_score=60.0,
        branding_score=40.0,
        content_score=45.0,
        conversion_score=35.0,
        overall_score=43.5,
        seo_issues=[
            {"type": "missing_title", "severity": "critical", "message": "Page has no <title>"},
            {"type": "missing_meta", "severity": "high", "message": "No meta description"},
        ],
        accessibility_issues=[
            {"rule": "image-alt", "impact": "serious", "description": "Images must have alt text"},
        ],
        performance_metrics={"lcp": 3.8, "fid": 120, "cls": 0.25, "ttfb": 1.2},
        recommendations=[
            {"category": "seo", "priority": "high", "title": "Add page title"},
            {"category": "mobile", "priority": "high", "title": "Fix mobile layout"},
        ],
        tech_stack=[{"name": "WordPress", "version": "5.9"}, {"name": "jQuery", "version": "1.12"}],
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    async_session.add(audit)
    # Mark the business as audited
    sample_business.audit_count = 1
    sample_business.last_audited_at = datetime.now(timezone.utc)
    async_session.add(sample_business)
    await async_session.commit()
    await async_session.refresh(audit)
    return audit


# ---------------------------------------------------------------------------
# Authenticated client helper
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
    test_client: AsyncClient, sample_user: User
) -> AsyncClient:
    """
    Return the test client with a pre-set Bearer JWT header for *sample_user*.

    No HTTP round-trip is required — the token is fabricated directly.
    """
    token = create_access_token(
        {"sub": str(sample_user.id), "email": sample_user.email}
    )
    test_client.headers.update({"Authorization": f"Bearer {token}"})
    return test_client
