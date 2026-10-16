"""
Tests for the business CRUD and search endpoints:
  GET    /api/v1/businesses
  POST   /api/v1/businesses
  GET    /api/v1/businesses/{id}
  PUT    /api/v1/businesses/{id}
  DELETE /api/v1/businesses/{id}
  GET    /api/v1/businesses/search
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Business

pytestmark = pytest.mark.asyncio

_BASE_URL = "/api/v1/businesses"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_create_payload(**overrides: Any) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "name": "Demo Bakery",
        "description": "Artisan bread since 1990",
        "industry": "food",
        "category": "bakery",
        "country": "US",
        "state": "CA",
        "city": "San Francisco",
        "phone": "+14155550199",
        "email": "hello@demobakery.example",
        "website_url": "https://demobakery.example",
    }
    base.update(overrides)
    return base


async def _create_business(client: AsyncClient, **overrides: Any) -> Dict[str, Any]:
    response = await client.post(_BASE_URL, json=_make_create_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_businesses_empty(authenticated_client: AsyncClient) -> None:
    """With no businesses in the DB the list returns an empty items array."""
    response = await authenticated_client.get(_BASE_URL)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_businesses_with_data(
    authenticated_client: AsyncClient, sample_business: Business
) -> None:
    """When businesses exist the list endpoint returns them."""
    response = await authenticated_client.get(_BASE_URL)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    ids = [item["id"] for item in data["items"]]
    assert str(sample_business.id) in ids


async def test_list_businesses_requires_auth(test_client: AsyncClient) -> None:
    """Unauthenticated requests to the list endpoint return 401."""
    response = await test_client.get(_BASE_URL)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


async def test_create_business(authenticated_client: AsyncClient) -> None:
    """POSTing a valid payload creates a business and returns 201."""
    payload = _make_create_payload(name="My New Shop")
    response = await authenticated_client.post(_BASE_URL, json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["name"] == "My New Shop"
    assert data["has_website"] is True
    assert "id" in data
    assert "slug" in data


async def test_create_business_no_website(authenticated_client: AsyncClient) -> None:
    """Creating a business without a website_url sets has_website=False."""
    payload = _make_create_payload(name="No-web Barber", website_url=None)
    response = await authenticated_client.post(_BASE_URL, json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["has_website"] is False


async def test_create_business_missing_name(authenticated_client: AsyncClient) -> None:
    """Omitting the required 'name' field returns 422."""
    payload = _make_create_payload()
    payload.pop("name")
    response = await authenticated_client.post(_BASE_URL, json=payload)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Get by ID
# ---------------------------------------------------------------------------


async def test_get_business(
    authenticated_client: AsyncClient, sample_business: Business
) -> None:
    """Fetching an existing business by ID returns its full data."""
    response = await authenticated_client.get(f"{_BASE_URL}/{sample_business.id}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == str(sample_business.id)
    assert data["name"] == sample_business.name


async def test_get_business_not_found(authenticated_client: AsyncClient) -> None:
    """Fetching a non-existent business returns 404."""
    response = await authenticated_client.get(f"{_BASE_URL}/{uuid.uuid4()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


async def test_update_business(
    authenticated_client: AsyncClient, sample_business: Business
) -> None:
    """Updating an existing business changes only the supplied fields."""
    response = await authenticated_client.put(
        f"{_BASE_URL}/{sample_business.id}",
        json={"name": "Acme Plumbing Renamed", "city": "Houston"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == "Acme Plumbing Renamed"
    assert data["city"] == "Houston"
    # Un-touched fields should be unchanged
    assert data["industry"] == sample_business.industry


async def test_update_business_not_found(authenticated_client: AsyncClient) -> None:
    """Updating a non-existent business returns 404."""
    response = await authenticated_client.put(
        f"{_BASE_URL}/{uuid.uuid4()}",
        json={"name": "Ghost"},
    )
    assert response.status_code == 404


async def test_update_business_sets_has_website(
    authenticated_client: AsyncClient, sample_business: Business
) -> None:
    """Setting website_url to None on update flips has_website to False."""
    response = await authenticated_client.put(
        f"{_BASE_URL}/{sample_business.id}",
        json={"website_url": None},
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_website"] is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


async def test_delete_business(
    authenticated_client: AsyncClient, sample_business: Business
) -> None:
    """Deleting an existing business returns 204."""
    response = await authenticated_client.delete(f"{_BASE_URL}/{sample_business.id}")
    assert response.status_code == 204

    # Subsequent GET should 404
    get_response = await authenticated_client.get(f"{_BASE_URL}/{sample_business.id}")
    assert get_response.status_code == 404


async def test_delete_business_not_found(authenticated_client: AsyncClient) -> None:
    """Deleting a non-existent business returns 404."""
    response = await authenticated_client.delete(f"{_BASE_URL}/{uuid.uuid4()}")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


async def test_search_businesses(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """Search returns businesses matching the query term."""
    # Seed two businesses
    b1 = Business(
        name="Austin Heating & Cooling",
        slug="austin-heating-cooling-s1",
        industry="hvac",
        city="Austin",
        has_website=True,
        discovered_at=datetime.now(timezone.utc),
    )
    b2 = Business(
        name="Dallas Bakery",
        slug="dallas-bakery-s1",
        industry="food",
        city="Dallas",
        has_website=False,
        discovered_at=datetime.now(timezone.utc),
    )
    async_session.add_all([b1, b2])
    await async_session.commit()

    response = await authenticated_client.get(
        f"{_BASE_URL}/search", params={"q": "austin"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] >= 1
    names = [item["name"] for item in data["items"]]
    assert "Austin Heating & Cooling" in names
    assert "Dallas Bakery" not in names


async def test_search_businesses_no_results(authenticated_client: AsyncClient) -> None:
    """A search term that matches nothing returns empty results."""
    response = await authenticated_client.get(
        f"{_BASE_URL}/search", params={"q": "zzz_nonexistent_zzz"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


async def test_search_businesses_missing_query(authenticated_client: AsyncClient) -> None:
    """Calling /search without ?q returns 422."""
    response = await authenticated_client.get(f"{_BASE_URL}/search")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Filter by industry
# ---------------------------------------------------------------------------


async def test_filter_by_industry(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """Filtering by industry returns only matching businesses."""
    b1 = Business(
        name="Legal Eagles LLC",
        slug="legal-eagles-fi1",
        industry="legal",
        has_website=True,
        discovered_at=datetime.now(timezone.utc),
    )
    b2 = Business(
        name="Tasty Burgers",
        slug="tasty-burgers-fi1",
        industry="restaurant",
        has_website=True,
        discovered_at=datetime.now(timezone.utc),
    )
    async_session.add_all([b1, b2])
    await async_session.commit()

    response = await authenticated_client.get(
        _BASE_URL, params={"industry": "legal"}
    )
    assert response.status_code == 200, response.text
    data = response.json()
    for item in data["items"]:
        assert item["industry"] == "legal"


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_pagination(
    authenticated_client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """page and page_size parameters work correctly."""
    businesses = [
        Business(
            name=f"Biz {i}",
            slug=f"biz-{i}-pg",
            has_website=False,
            discovered_at=datetime.now(timezone.utc),
        )
        for i in range(5)
    ]
    async_session.add_all(businesses)
    await async_session.commit()

    # Page 1, size 3
    r1 = await authenticated_client.get(_BASE_URL, params={"page": 1, "page_size": 3})
    assert r1.status_code == 200
    d1 = r1.json()
    assert len(d1["items"]) == 3
    assert d1["total"] >= 5

    # Page 2, size 3
    r2 = await authenticated_client.get(_BASE_URL, params={"page": 2, "page_size": 3})
    assert r2.status_code == 200
    d2 = r2.json()
    # Items on page 2 are distinct from items on page 1
    ids_page1 = {item["id"] for item in d1["items"]}
    ids_page2 = {item["id"] for item in d2["items"]}
    assert ids_page1.isdisjoint(ids_page2)
