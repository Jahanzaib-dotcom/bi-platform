"""
Pydantic v2 schemas for Audit Reports.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AuditRequest(BaseModel):
    """Body for triggering a new audit on a business."""

    business_id: uuid.UUID
    force: bool = Field(
        default=False,
        description="Re-run even if a recent completed audit exists.",
    )
    include_screenshot: bool = True
    include_ai_analysis: bool = True


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AuditSummary(BaseModel):
    """Lightweight audit representation used in list responses."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    business_id: uuid.UUID
    status: str
    overall_score: Optional[float] = None
    seo_score: Optional[float] = None
    accessibility_score: Optional[float] = None
    speed_score: Optional[float] = None
    security_score: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime


class AuditReportResponse(BaseModel):
    """Full audit report returned by the API."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    business_id: uuid.UUID
    status: str

    # URLs
    website_url: Optional[str] = None
    screenshot_desktop_url: Optional[str] = None
    screenshot_mobile_url: Optional[str] = None

    # Scores
    ui_score: Optional[float] = None
    ux_score: Optional[float] = None
    mobile_score: Optional[float] = None
    seo_score: Optional[float] = None
    accessibility_score: Optional[float] = None
    speed_score: Optional[float] = None
    security_score: Optional[float] = None
    branding_score: Optional[float] = None
    content_score: Optional[float] = None
    conversion_score: Optional[float] = None
    overall_score: Optional[float] = None

    # Detailed findings
    seo_issues: Optional[List[Dict[str, Any]]] = None
    accessibility_issues: Optional[List[Dict[str, Any]]] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None
    ai_analysis: Optional[Dict[str, Any]] = None
    tech_stack: Optional[List[Dict[str, Any]]] = None
    broken_links: Optional[List[Dict[str, Any]]] = None

    # Error info
    error_message: Optional[str] = None

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
