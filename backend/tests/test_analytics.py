"""
Tests for the analytics endpoints:
  GET /api/v1/analytics/dashboard
  GET /api/v1/analytics/industries
  GET /api/v1/analytics/geography
  GET /api/v1/analytics/opportunities
  GET /api/v1/analytics/trends
  GET /api/v1/analytics/revenue
  GET /api/v1/analytics/scores-distribution
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business
from app.models.discovery_job import DiscoveryJob, JobStatus
from app.models.user import User

pytestmark = pytest.mark.asyncio

_ANALYTICS = "/api/v1/analytics"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_businesses(session: AsyncSession, user: User) -> None:
    """Insert a small set of diverse businesses for analytics queries."""
    rows = [
        Business(
            name="Legal Eagles", slug="legal-eagles-an",
            industry="legal", country="US", state="TX", city="Austin",
            has_website=True, overall_score=75.0, opportunity_score=40.0,
            revenue_potential=12000.0, audit_count=1,
            discovered_at=datetime.now(timezone.utc),
        ),
        Business(
            name="Quick Bites", slug="quick-bites-an",
            industry="restaurant", country="US", state="CA", city="San Francisco",
            has_website=False, overall_score=None, opportunity_score=85.0,
            revenue_potential=4500.0, audit_count=0,
            discovered_at=datetime.now(timezone.utc),
        ),
        Business(
            name="Plumb Perfect", slug="plumb-perfect-an",
            industry="plumbing", country="US", state="TX", city="Houston",
            has_website=True, overall_score=30.0, opportunity_score=70.0,
            revenue_potential=7000.0, audit_count=1,
            discovered_at=datetime.now(timezone.utc),
        ),
        Business(
            name="Bloom Flowers", slug="bloom-flowers-an",
            industry="retail", country="CA", state="ON", city="Toronto",
            has_website=True, overall_score=60.0, opportunity_score=55.0,
            revenue_potential=5000.0, audit_count=0,
            discovered_at=datetime.now(timezone.utc),
        ),
    ]
    session.add_all(rows)
    await session.flush()

    # Add a completed audit for businesses with audit_count > 0
    for biz in rows:
        if biz.audit_count > 0:
            audit = AuditReport(
                business_id=biz.id,
                status=AuditStatus.completed,
                overall_score=biz.overall_score,
                completed_at=datetime.now(timezone.utc),
            )
            session.add(audit)

    # Add a discovery job
    job = DiscoveryJob(
        user_id=user.id,
        name="Test discovery job",
        status=JobStatus.completed,
    )
    session.add(job)

    await session.commit()


# ---------------------------------------------------------------------------
# Dashboard KPIs
# ---------------------------------------------------------------------------


async def test_dashboard_stats_empty(authenticated_client: AsyncClient) -> None:
    """Dashboard with no data returns zero counts and None for averages."""
    response = await authenticated_client.get(f"{_ANALYTICS}/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_businesses"] == 0
    assert data["total_audited"] == 0
    assert data["total_without_website"] == 0
    assert data["avg_overall_score"] is None
    assert data["avg_opportunity_score"] is None


async def test_dashboard_stats_with_data(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """Dashboard counts are correct when businesses exist."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/dashboard")
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["total_businesses"] == 4
    assert data["total_without_website"] == 1   # Quick Bites
    assert data["total_with_website"] == 3
    assert data["total_audited"] == 2           # audit_count > 0
    assert data["total_discovery_jobs"] >= 1
    assert data["avg_overall_score"] is not None
    assert isinstance(data["avg_overall_score"], float)


async def test_dashboard_stats_requires_auth(test_client: AsyncClient) -> None:
    """Unauthenticated requests return 401."""
    response = await test_client.get(f"{_ANALYTICS}/dashboard")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Industry breakdown
# ---------------------------------------------------------------------------


async def test_industry_breakdown(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """industries endpoint returns a grouped breakdown with correct fields."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/industries")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] > 0

    # Verify shape of each item
    for item in data["items"]:
        assert "industry" in item
        assert isinstance(item["count"], int)
        assert item["count"] > 0


async def test_industry_breakdown_limit(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """The ?limit parameter caps the number of returned industries."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(
        f"{_ANALYTICS}/industries", params={"limit": 2}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 2


async def test_industry_breakdown_empty_db(authenticated_client: AsyncClient) -> None:
    """With no data the industries breakdown returns an empty items list."""
    response = await authenticated_client.get(f"{_ANALYTICS}/industries")
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


# ---------------------------------------------------------------------------
# Geography breakdown
# ---------------------------------------------------------------------------


async def test_geography_breakdown_by_country(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """Default geography breakdown groups by country."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/geography")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["group_by"] == "country"
    assert len(data["items"]) > 0
    locations = [item["location"] for item in data["items"]]
    assert "US" in locations or "CA" in locations


async def test_geography_breakdown_by_city(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """Geography breakdown by city returns city-level grouping."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(
        f"{_ANALYTICS}/geography", params={"group_by": "city"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["group_by"] == "city"


async def test_geography_breakdown_invalid_group_by(
    authenticated_client: AsyncClient,
) -> None:
    """An invalid group_by value returns 422."""
    response = await authenticated_client.get(
        f"{_ANALYTICS}/geography", params={"group_by": "zip"}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Opportunity breakdown
# ---------------------------------------------------------------------------


async def test_opportunity_breakdown_structure(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """Opportunity breakdown returns the expected tier structure."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/opportunities")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "total" in data
    assert "breakdown" in data

    tier_types = {item["type"] for item in data["breakdown"]}
    assert "no_website" in tier_types
    assert "low_score" in tier_types
    assert "medium_score" in tier_types
    assert "high_score" in tier_types
    assert "not_yet_audited" in tier_types


async def test_opportunity_breakdown_totals_consistent(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """The sum of tier counts should be <= total (overlaps are not possible)."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/opportunities")
    assert response.status_code == 200
    data = response.json()
    total = data["total"]
    tier_sum = sum(item["count"] for item in data["breakdown"])
    assert tier_sum <= total


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------


async def test_trends_endpoint(
    authenticated_client: AsyncClient,
) -> None:
    """Trends endpoint returns the expected structure."""
    response = await authenticated_client.get(f"{_ANALYTICS}/trends")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "period_days" in data
    assert data["period_days"] == 30
    assert "businesses_discovered" in data
    assert "audits_completed" in data
    assert isinstance(data["businesses_discovered"], list)
    assert isinstance(data["audits_completed"], list)


async def test_trends_custom_days(authenticated_client: AsyncClient) -> None:
    """The ?days parameter controls the look-back window."""
    response = await authenticated_client.get(
        f"{_ANALYTICS}/trends", params={"days": 60}
    )
    assert response.status_code == 200
    assert response.json()["period_days"] == 60


async def test_trends_invalid_days(authenticated_client: AsyncClient) -> None:
    """days < 7 returns 422."""
    response = await authenticated_client.get(
        f"{_ANALYTICS}/trends", params={"days": 3}
    )
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Revenue estimates
# ---------------------------------------------------------------------------


async def test_revenue_estimates(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """Revenue estimates endpoint returns industry-grouped data."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/revenue")
    assert response.status_code == 200, response.text
    data = response.json()
    assert "items" in data
    assert "grand_total_revenue_potential" in data
    assert data["grand_total_revenue_potential"] >= 0


async def test_revenue_estimates_empty(authenticated_client: AsyncClient) -> None:
    """With no revenue data the grand total is 0."""
    response = await authenticated_client.get(f"{_ANALYTICS}/revenue")
    assert response.status_code == 200
    data = response.json()
    assert data["grand_total_revenue_potential"] == 0.0
    assert data["items"] == []


# ---------------------------------------------------------------------------
# Scores distribution
# ---------------------------------------------------------------------------


async def test_scores_distribution(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
    sample_user: User,
) -> None:
    """Scores distribution returns a histogram with the requested bucket count."""
    await _seed_businesses(async_session, sample_user)

    response = await authenticated_client.get(f"{_ANALYTICS}/scores-distribution")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["score_field"] == "overall_score"
    assert len(data["histogram"]) == data["buckets"]


async def test_scores_distribution_custom_buckets(
    authenticated_client: AsyncClient,
) -> None:
    """The ?buckets parameter controls histogram size."""
    response = await authenticated_client.get(
        f"{_ANALYTICS}/scores-distribution", params={"buckets": 5}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["histogram"]) == 5


async def test_scores_distribution_invalid_field(
    authenticated_client: AsyncClient,
) -> None:
    """An invalid score_field parameter returns 422."""
    response = await authenticated_client.get(
        f"{_ANALYTICS}/scores-distribution", params={"score_field": "bad_field"}
    )
    assert response.status_code == 422
