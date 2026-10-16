"""
Pydantic v2 schemas for analytics and dashboard data.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Dashboard overview
# ---------------------------------------------------------------------------


class DashboardStats(BaseModel):
    """Aggregate platform-level statistics for the main dashboard."""

    total_businesses: int
    businesses_with_website: int
    businesses_without_website: int
    total_audits: int
    audits_completed: int
    audits_pending: int
    audits_failed: int
    total_discovery_jobs: int
    active_discovery_jobs: int
    avg_overall_score: Optional[float] = None
    avg_opportunity_score: Optional[float] = None
    high_opportunity_count: int = Field(
        description="Businesses with opportunity_score >= 70."
    )
    # Delta values (percentage change vs previous period)
    businesses_delta_pct: Optional[float] = None
    audits_delta_pct: Optional[float] = None


# ---------------------------------------------------------------------------
# Industry breakdown
# ---------------------------------------------------------------------------


class IndustryStats(BaseModel):
    """Aggregated statistics for a single industry."""

    industry: str
    business_count: int
    avg_score: Optional[float] = None
    avg_opportunity_score: Optional[float] = None
    website_coverage_pct: float = Field(
        description="Percentage of businesses in this industry that have a website."
    )
    top_cities: List[str] = []


# ---------------------------------------------------------------------------
# Geographic breakdown
# ---------------------------------------------------------------------------


class GeoStats(BaseModel):
    """Aggregated statistics for a geographic region."""

    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    business_count: int
    avg_score: Optional[float] = None
    opportunity_index: Optional[float] = Field(
        default=None,
        description="Composite index combining density and average opportunity score.",
    )


# ---------------------------------------------------------------------------
# Trend data
# ---------------------------------------------------------------------------


class TrendPoint(BaseModel):
    """A single data point in a time series."""

    date: str = Field(description="ISO-8601 date string (YYYY-MM-DD).")
    value: float


class TrendData(BaseModel):
    """Time-series data for a named metric."""

    metric: str
    unit: Optional[str] = None
    points: List[TrendPoint]
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Opportunity breakdown
# ---------------------------------------------------------------------------


class OpportunityTier(BaseModel):
    """Stats for a single opportunity tier (low / medium / high / critical)."""

    tier: str  # e.g. "high", "medium", "low"
    min_score: float
    max_score: float
    count: int
    pct_of_total: float


class OpportunityBreakdown(BaseModel):
    """Full breakdown of businesses across opportunity tiers."""

    total: int
    tiers: List[OpportunityTier]
    avg_revenue_potential: Optional[float] = None
    top_industries: List[str] = []
    top_locations: List[str] = []
