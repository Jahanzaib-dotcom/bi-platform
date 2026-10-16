"""
Pydantic v2 schemas for the Business domain.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Enumerations (mirrored from ORM to avoid ORM import in schemas)
# ---------------------------------------------------------------------------


class WebsiteStatusEnum(str):
    active = "active"
    inactive = "inactive"
    parked = "parked"
    abandoned = "abandoned"
    missing = "missing"


# ---------------------------------------------------------------------------
# Write / mutation schemas
# ---------------------------------------------------------------------------


class BusinessCreate(BaseModel):
    """Payload for creating a new business."""

    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None

    industry: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    subcategory: Optional[str] = Field(default=None, max_length=100)

    country: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    zip_code: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = None

    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    website_url: Optional[str] = None

    has_website: bool = False
    social_profiles: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class BusinessUpdate(BaseModel):
    """Payload for partially updating an existing business."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None

    industry: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    subcategory: Optional[str] = Field(default=None, max_length=100)

    country: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    city: Optional[str] = Field(default=None, max_length=100)
    zip_code: Optional[str] = Field(default=None, max_length=20)
    address: Optional[str] = None

    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    website_url: Optional[str] = None

    has_website: Optional[bool] = None
    website_status: Optional[str] = None
    social_profiles: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# Read / response schemas
# ---------------------------------------------------------------------------


class BusinessSummary(BaseModel):
    """Lightweight representation used in list responses."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    slug: str
    industry: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    has_website: bool
    website_status: Optional[str] = None
    overall_score: Optional[float] = None
    opportunity_score: Optional[float] = None
    audit_count: int
    created_at: datetime


class BusinessResponse(BaseModel):
    """Full business record returned by the API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str] = None

    industry: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None

    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    address: Optional[str] = None

    phone: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = None

    has_website: bool
    website_status: Optional[str] = None
    social_profiles: Optional[Dict[str, Any]] = None

    source: Optional[str] = None
    source_id: Optional[str] = None
    source_url: Optional[str] = None

    discovered_at: Optional[datetime] = None
    last_audited_at: Optional[datetime] = None

    overall_score: Optional[float] = None
    opportunity_score: Optional[float] = None
    priority_score: Optional[float] = None
    revenue_potential: Optional[float] = None

    audit_count: int
    tags: Optional[List[str]] = None

    created_at: datetime
    updated_at: datetime


class BusinessListResponse(BaseModel):
    """Paginated list of businesses."""

    items: List[BusinessSummary]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def from_page(
        cls,
        items: List[BusinessSummary],
        total: int,
        page: int,
        page_size: int,
    ) -> "BusinessListResponse":
        pages = max(1, (total + page_size - 1) // page_size)
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


# ---------------------------------------------------------------------------
# Filter / query params
# ---------------------------------------------------------------------------


class BusinessFilter(BaseModel):
    """Query parameters for filtering and sorting the business list."""

    # Pagination
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)

    # Search
    q: Optional[str] = Field(default=None, description="Full-text search term")

    # Filters
    industry: Optional[str] = None
    category: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    has_website: Optional[bool] = None
    website_status: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[List[str]] = None

    # Score range filters
    min_score: Optional[float] = Field(default=None, ge=0, le=100)
    max_score: Optional[float] = Field(default=None, ge=0, le=100)

    # Sorting
    sort_by: str = Field(default="created_at")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")
