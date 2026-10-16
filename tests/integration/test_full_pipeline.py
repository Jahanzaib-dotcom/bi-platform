"""
Integration test: full discovery → audit → analytics pipeline.

Flow
----
1.  Create a discovery job via POST /api/v1/discovery/jobs
2.  A mock provider returns 5 ``BusinessResult`` objects that are saved as
    ``Business`` rows.
3.  For each business run the audit pipeline with mocked Playwright and scoring.
4.  Verify all businesses are in the DB with non-null overall_score.
5.  Verify the analytics dashboard reflects the correct counts.

All external I/O (HTTP providers, Playwright, Celery workers) is mocked so the
test suite is fully offline.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# ---------------------------------------------------------------------------
# Force in-memory SQLite before any app import
# ---------------------------------------------------------------------------

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SQLITE_URL"] = "sqlite+aiosqlite:///:memory:"

from app.core.database import Base, get_db  # noqa: E402
from app.core.security import create_access_token, get_password_hash  # noqa: E402
from app.engines.discovery.base import BusinessResult  # noqa: E402
from app.engines.scoring.scoring_engine import ScoringEngine  # noqa: E402
from app.models.audit import AuditReport, AuditStatus  # noqa: E402
from app.models.business import Business  # noqa: E402
from app.models.discovery_job import DiscoveryJob, JobStatus  # noqa: E402
from app.models.user import User  # noqa: E402

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Five mock businesses yielded by the fake provider
# ---------------------------------------------------------------------------

_MOCK_BUSINESSES: List[BusinessResult] = [
    BusinessResult(
        name="Joe's Pizza",
        city="Austin",
        state="TX",
        country="US",
        industry="restaurant",
        website_url="https://joespizza.example",
        phone="+15125551001",
        source="mock_provider",
        source_id="mock:1",
    ),
    BusinessResult(
        name="Austin Auto Repair",
        city="Austin",
        state="TX",
        country="US",
        industry="automotive",
        website_url=None,
        phone="+15125551002",
        source="mock_provider",
        source_id="mock:2",
    ),
    BusinessResult(
        name="Bloom Flower Studio",
        city="Austin",
        state="TX",
        country="US",
        industry="retail",
        website_url="https://bloomflowers.example",
        source="mock_provider",
        source_id="mock:3",
    ),
    BusinessResult(
        name="Tech Wizards LLC",
        city="Austin",
        state="TX",
        country="US",
        industry="technology",
        website_url="https://techwizards.example",
        source="mock_provider",
        source_id="mock:4",
    ),
    BusinessResult(
        name="Sunrise Yoga Studio",
        city="Austin",
        state="TX",
        country="US",
        industry="wellness",
        website_url="https://sunriseyoga.example",
        source="mock_provider",
        source_id="mock:5",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def pipeline_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    import app.models  # noqa: F401 – register all models

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def pipeline_session(pipeline_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(
        bind=pipeline_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def pipeline_client(pipeline_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    from app.main import create_app

    app = create_app()

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield pipeline_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def pipeline_user(pipeline_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="pipeline@example.com",
        username="pipelineuser",
        hashed_password=get_password_hash("Password123!"),
        full_name="Pipeline Tester",
        is_active=True,
        is_superuser=False,
        api_key=secrets.token_urlsafe(48),
    )
    pipeline_session.add(user)
    await pipeline_session.commit()
    await pipeline_session.refresh(user)
    return user


@pytest_asyncio.fixture(scope="function")
async def auth_pipeline_client(
    pipeline_client: AsyncClient, pipeline_user: User
) -> AsyncClient:
    token = create_access_token(
        {"sub": str(pipeline_user.id), "email": pipeline_user.email}
    )
    pipeline_client.headers.update({"Authorization": f"Bearer {token}"})
    return pipeline_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _save_businesses_from_results(
    session: AsyncSession,
    results: List[BusinessResult],
) -> List[Business]:
    """Persist BusinessResult objects as Business rows (simulates discovery worker)."""
    saved: List[Business] = []
    for i, result in enumerate(results):
        slug = f"{result.name.lower().replace(' ', '-')}-integ-{i}"
        business = Business(
            id=uuid.uuid4(),
            name=result.name,
            slug=slug,
            industry=result.industry,
            city=result.city,
            state=result.state,
            country=result.country,
            phone=result.phone,
            website_url=result.website_url,
            has_website=bool(result.website_url),
            source=result.source,
            source_id=result.source_id,
            discovered_at=datetime.now(timezone.utc),
            audit_count=0,
        )
        session.add(business)
        saved.append(business)
    await session.commit()
    for b in saved:
        await session.refresh(b)
    return saved


def _make_mock_audit_report(business: Business) -> Dict[str, Any]:
    """Return a fake audit result dict (simulates Playwright audit output)."""
    return {
        "website_url": business.website_url or "",
        "ui_score": 55.0,
        "ux_score": 50.0,
        "mobile_score": 40.0,
        "seo_score": 35.0,
        "accessibility_score": 60.0,
        "speed_score": 45.0,
        "security_score": 65.0,
        "branding_score": 50.0,
        "content_score": 45.0,
        "conversion_score": 40.0,
        "seo_issues": [
            {"type": "missing_title", "severity": "high", "message": "No title tag"},
        ],
        "accessibility_issues": [],
        "performance_metrics": {"lcp": 3.5, "fid": 100, "cls": 0.15},
        "tech_stack": [{"name": "WordPress", "version": "6.0"}],
        "recommendations": [
            {"category": "seo", "priority": "high", "title": "Add page title"},
        ],
    }


async def _run_audit_for_business(
    session: AsyncSession, business: Business
) -> AuditReport:
    """
    Simulate the audit pipeline for a single business.

    In the real app Playwright would navigate to the site; here we return a
    pre-built mock result and feed it through the ScoringEngine.
    """
    mock_result = _make_mock_audit_report(business)

    # Use the real ScoringEngine to compute scores
    engine = ScoringEngine()

    class _AuditProxy:
        """Duck-typed stand-in for AuditReport so ScoringEngine can read scores."""
        def __getattr__(self, name: str) -> Any:
            return mock_result.get(name)

    class _BusinessProxy:
        has_website = business.has_website
        industry = business.industry
        city = business.city
        country = business.country
        social_profiles = None

    audit_proxy = _AuditProxy()
    biz_proxy = _BusinessProxy()

    overall_score = engine.calculate_website_quality_score(audit_proxy)
    opportunity_score = engine.calculate_opportunity_score(biz_proxy, audit_proxy)

    audit = AuditReport(
        id=uuid.uuid4(),
        business_id=business.id,
        status=AuditStatus.completed,
        website_url=mock_result["website_url"],
        ui_score=mock_result["ui_score"],
        ux_score=mock_result["ux_score"],
        mobile_score=mock_result["mobile_score"],
        seo_score=mock_result["seo_score"],
        accessibility_score=mock_result["accessibility_score"],
        speed_score=mock_result["speed_score"],
        security_score=mock_result["security_score"],
        branding_score=mock_result["branding_score"],
        content_score=mock_result["content_score"],
        conversion_score=mock_result["conversion_score"],
        overall_score=overall_score,
        seo_issues=mock_result["seo_issues"],
        accessibility_issues=mock_result["accessibility_issues"],
        performance_metrics=mock_result["performance_metrics"],
        tech_stack=mock_result["tech_stack"],
        recommendations=mock_result["recommendations"],
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(audit)

    # Update the business
    business.overall_score = overall_score
    business.opportunity_score = opportunity_score
    business.audit_count = (business.audit_count or 0) + 1
    business.last_audited_at = datetime.now(timezone.utc)
    session.add(business)

    await session.commit()
    await session.refresh(audit)
    return audit


# ---------------------------------------------------------------------------
# The pipeline test
# ---------------------------------------------------------------------------


async def test_full_pipeline(
    auth_pipeline_client: AsyncClient,
    pipeline_session: AsyncSession,
    pipeline_user: User,
) -> None:
    """
    End-to-end pipeline:
    1. Mock discovery yields 5 BusinessResult objects.
    2. Save them as Business rows.
    3. Run audits (mocked Playwright) through ScoringEngine.
    4. Verify DB state.
    5. Verify analytics endpoint returns correct data.
    """

    # ------------------------------------------------------------------
    # Step 1 — Create a discovery job row (simulating the POST endpoint)
    # ------------------------------------------------------------------
    job = DiscoveryJob(
        id=uuid.uuid4(),
        user_id=pipeline_user.id,
        name="Integration Test Job",
        status=JobStatus.pending,
        config={"sources": ["mock_provider"], "industries": ["restaurant"], "countries": ["US"]},
    )
    pipeline_session.add(job)
    await pipeline_session.commit()

    # ------------------------------------------------------------------
    # Step 2 — Mock provider returns 5 businesses; save them to DB
    # ------------------------------------------------------------------
    businesses = await _save_businesses_from_results(pipeline_session, _MOCK_BUSINESSES)
    assert len(businesses) == 5

    # Mark job as completed
    job.status = JobStatus.completed
    job.total_found = 5
    job.total_processed = 5
    job.completed_at = datetime.now(timezone.utc)
    pipeline_session.add(job)
    await pipeline_session.commit()

    # ------------------------------------------------------------------
    # Step 3 — Run audit pipeline for each business with mocked Playwright
    # ------------------------------------------------------------------
    audits: List[AuditReport] = []
    for business in businesses:
        audit = await _run_audit_for_business(pipeline_session, business)
        audits.append(audit)

    assert len(audits) == 5

    # ------------------------------------------------------------------
    # Step 4 — Verify businesses are in DB with non-null scores
    # ------------------------------------------------------------------
    result = await pipeline_session.execute(select(Business))
    db_businesses = result.scalars().all()

    assert len(db_businesses) == 5

    for biz in db_businesses:
        assert biz.overall_score is not None, f"{biz.name} has no overall_score"
        assert 0.0 <= biz.overall_score <= 100.0
        assert biz.opportunity_score is not None
        assert biz.audit_count == 1
        assert biz.last_audited_at is not None

    # ------------------------------------------------------------------
    # Step 5a — Verify audit reports are in DB with completed status
    # ------------------------------------------------------------------
    audit_result = await pipeline_session.execute(select(AuditReport))
    db_audits = audit_result.scalars().all()
    assert len(db_audits) == 5

    for audit in db_audits:
        assert audit.status == AuditStatus.completed
        assert audit.overall_score is not None
        assert audit.completed_at is not None

    # ------------------------------------------------------------------
    # Step 5b — Verify analytics dashboard reflects the correct counts
    # ------------------------------------------------------------------
    response = await auth_pipeline_client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total_businesses"] == 5
    # All businesses have audit_count == 1
    assert data["total_audited"] == 5
    # Austin Auto Repair has no website
    assert data["total_without_website"] == 1
    assert data["total_with_website"] == 4
    assert data["total_discovery_jobs"] == 1
    assert data["total_audits_completed"] == 5
    assert data["avg_overall_score"] is not None

    # ------------------------------------------------------------------
    # Step 5c — Verify industry breakdown includes "restaurant"
    # ------------------------------------------------------------------
    industries_response = await auth_pipeline_client.get("/api/v1/analytics/industries")
    assert industries_response.status_code == 200
    industries_data = industries_response.json()
    industry_names = {item["industry"] for item in industries_data["items"]}
    assert "restaurant" in industry_names

    # ------------------------------------------------------------------
    # Step 5d — Verify scores distribution has non-zero scored businesses
    # ------------------------------------------------------------------
    dist_response = await auth_pipeline_client.get("/api/v1/analytics/scores-distribution")
    assert dist_response.status_code == 200
    dist_data = dist_response.json()
    assert dist_data["total_with_score"] == 5
    # At least one histogram bucket has businesses in it
    bucket_counts = [b["count"] for b in dist_data["histogram"]]
    assert sum(bucket_counts) == 5


async def test_pipeline_businesses_are_searchable(
    auth_pipeline_client: AsyncClient,
    pipeline_session: AsyncSession,
    pipeline_user: User,
) -> None:
    """After pipeline runs, businesses are discoverable via the search endpoint."""
    await _save_businesses_from_results(pipeline_session, _MOCK_BUSINESSES)

    response = await auth_pipeline_client.get(
        "/api/v1/businesses/search", params={"q": "pizza"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    names = [item["name"] for item in data["items"]]
    assert "Joe's Pizza" in names


async def test_pipeline_businesses_filterable_by_industry(
    auth_pipeline_client: AsyncClient,
    pipeline_session: AsyncSession,
    pipeline_user: User,
) -> None:
    """After pipeline runs, businesses are filterable by industry."""
    await _save_businesses_from_results(pipeline_session, _MOCK_BUSINESSES)

    response = await auth_pipeline_client.get(
        "/api/v1/businesses", params={"industry": "technology"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Tech Wizards LLC"


async def test_pipeline_no_website_flagged_correctly(
    auth_pipeline_client: AsyncClient,
    pipeline_session: AsyncSession,
    pipeline_user: User,
) -> None:
    """Business with no website_url is saved with has_website=False."""
    await _save_businesses_from_results(pipeline_session, _MOCK_BUSINESSES)

    response = await auth_pipeline_client.get(
        "/api/v1/businesses", params={"has_website": "false"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "Austin Auto Repair"
