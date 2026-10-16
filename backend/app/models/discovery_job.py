from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.discovery_result import DiscoveryResult
    from app.models.user import User


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class DiscoveryJob(BaseModel):
    __tablename__ = "discovery_jobs"

    # ----- Foreign key -----
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ----- Identity -----
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # ----- Status -----
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status_enum"),
        default=JobStatus.pending,
        nullable=False,
        index=True,
    )

    # ----- Configuration -----
    # Shape: {sources, countries, industries, keywords, max_results}
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Progress counters -----
    total_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ----- Timing -----
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_completion: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Error / diagnostics -----
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logs: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Relationships -----
    user: Mapped["User"] = relationship(
        "User",
        back_populates="discovery_jobs",
    )
    discovery_results: Mapped[List["DiscoveryResult"]] = relationship(
        "DiscoveryResult",
        back_populates="job",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<DiscoveryJob id={self.id} name={self.name!r} "
            f"status={self.status.value!r}>"
        )
