"""
Pydantic v2 schemas for the Discovery engine.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration sub-schema
# ---------------------------------------------------------------------------


class DiscoveryConfig(BaseModel):
    """Fine-grained parameters for a discovery run."""

    sources: List[str] = Field(
        default=["web_search", "duckduckgo"],
        description="List of discovery source identifiers to enable.",
    )
    countries: Optional[List[str]] = Field(
        default=None,
        description="ISO-3166-1 alpha-2 country codes to filter results.",
    )
    industries: Optional[List[str]] = Field(
        default=None,
        description="Industry keywords to target.",
    )
    keywords: Optional[List[str]] = Field(
        default=None,
        description="Additional free-form search keywords.",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=10_000,
        description="Maximum number of businesses to discover in this job.",
    )
    dedup_enabled: bool = Field(
        default=True,
        description="Skip businesses already present in the database.",
    )
    auto_audit: bool = Field(
        default=False,
        description="Automatically queue an audit for each discovered business.",
    )


# ---------------------------------------------------------------------------
# Request / write schemas
# ---------------------------------------------------------------------------


class DiscoveryJobCreate(BaseModel):
    """Payload for creating a new discovery job."""

    name: str = Field(min_length=1, max_length=255)
    config: DiscoveryConfig = Field(default_factory=DiscoveryConfig)


# ---------------------------------------------------------------------------
# Status / response schemas
# ---------------------------------------------------------------------------


class DiscoveryJobStatus(BaseModel):
    """Real-time progress snapshot of a discovery job."""

    id: uuid.UUID
    status: str
    total_found: int
    total_processed: int
    total_errors: int
    progress_pct: float = Field(
        description="Percentage complete (0–100). 0 when total_found == 0.",
    )
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None

    @classmethod
    def from_orm(cls, job) -> "DiscoveryJobStatus":  # type: ignore[override]
        total = job.total_found or 0
        processed = job.total_processed or 0
        pct = round((processed / total * 100) if total > 0 else 0.0, 1)
        return cls(
            id=job.id,
            status=job.status,
            total_found=total,
            total_processed=processed,
            total_errors=job.total_errors or 0,
            progress_pct=pct,
            started_at=job.started_at,
            estimated_completion=job.estimated_completion,
        )


class DiscoveryJobResponse(BaseModel):
    """Full discovery job record returned by the API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    status: str
    config: Optional[Dict[str, Any]] = None

    total_found: int
    total_processed: int
    total_errors: int

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    error_message: Optional[str] = None

    created_at: datetime
    updated_at: datetime
