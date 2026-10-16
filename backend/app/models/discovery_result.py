from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.discovery_job import DiscoveryJob


class ResultStatus(str, enum.Enum):
    pending = "pending"
    processed = "processed"
    duplicate = "duplicate"
    failed = "failed"


class DiscoveryResult(BaseModel):
    __tablename__ = "discovery_results"

    # ----- Foreign keys -----
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("discovery_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("businesses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ----- Raw scraped payload -----
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Provenance -----
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ----- Status -----
    status: Mapped[ResultStatus] = mapped_column(
        Enum(ResultStatus, name="result_status_enum"),
        default=ResultStatus.pending,
        nullable=False,
        index=True,
    )

    # ----- Timing -----
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Relationships -----
    job: Mapped["DiscoveryJob"] = relationship(
        "DiscoveryJob",
        back_populates="discovery_results",
    )
    business: Mapped[Optional["Business"]] = relationship(
        "Business",
        foreign_keys=[business_id],
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"<DiscoveryResult id={self.id} job_id={self.job_id} "
            f"status={self.status.value!r}>"
        )
