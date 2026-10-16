from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.screenshot import Screenshot


class AuditStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class AuditReport(BaseModel):
    __tablename__ = "audit_reports"

    # ----- Foreign key -----
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ----- Status -----
    status: Mapped[AuditStatus] = mapped_column(
        Enum(AuditStatus, name="audit_status_enum"),
        default=AuditStatus.pending,
        nullable=False,
        index=True,
    )

    # ----- URLs -----
    website_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_desktop_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    screenshot_mobile_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Scores (0–100) -----
    ui_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ux_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    mobile_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    seo_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    accessibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    speed_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    security_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    branding_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    content_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conversion_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ----- Issue arrays -----
    # Each element: {type, severity, message, selector?, url?}
    seo_issues: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    # Each element: {rule, impact, description, nodes?}
    accessibility_issues: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Performance metrics -----
    # Shape: {lcp, fid, cls, ttfb, page_size, requests}
    performance_metrics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Recommendations -----
    # Each element: {category, priority, title, description}
    recommendations: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- AI analysis -----
    # Shape: {strengths, weaknesses, opportunities, estimated_value}
    ai_analysis: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Tech detection -----
    tech_stack: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Broken links -----
    broken_links: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Timing -----
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Error -----
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Relationships -----
    business: Mapped["Business"] = relationship(
        "Business",
        back_populates="audits",
    )
    screenshots: Mapped[List["Screenshot"]] = relationship(
        "Screenshot",
        back_populates="audit",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "business_id": str(self.business_id),
            "status": self.status.value,
            "website_url": self.website_url,
            "screenshot_desktop_url": self.screenshot_desktop_url,
            "screenshot_mobile_url": self.screenshot_mobile_url,
            "ui_score": self.ui_score,
            "ux_score": self.ux_score,
            "mobile_score": self.mobile_score,
            "seo_score": self.seo_score,
            "accessibility_score": self.accessibility_score,
            "speed_score": self.speed_score,
            "security_score": self.security_score,
            "branding_score": self.branding_score,
            "content_score": self.content_score,
            "conversion_score": self.conversion_score,
            "overall_score": self.overall_score,
            "recommendations": self.recommendations,
            "ai_analysis": self.ai_analysis,
            "tech_stack": self.tech_stack,
            "performance_metrics": self.performance_metrics,
            "seo_issues": self.seo_issues,
            "accessibility_issues": self.accessibility_issues,
            "broken_links": self.broken_links,
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat(),
        }

    def __repr__(self) -> str:
        return (
            f"<AuditReport id={self.id} business_id={self.business_id} "
            f"status={self.status.value!r}>"
        )
