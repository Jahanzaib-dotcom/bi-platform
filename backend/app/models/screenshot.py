from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.audit import AuditReport
    from app.models.business import Business


class Viewport(str, enum.Enum):
    desktop = "desktop"
    mobile = "mobile"
    tablet = "tablet"
    full_page = "full_page"


class Screenshot(BaseModel):
    __tablename__ = "screenshots"

    # ----- Foreign keys -----
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    audit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("audit_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ----- Viewport classification -----
    viewport: Mapped[Viewport] = mapped_column(
        Enum(Viewport, name="viewport_enum"),
        nullable=False,
        index=True,
    )

    # ----- Storage -----
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes

    # ----- Dimensions -----
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ----- Capture metadata -----
    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Relationships -----
    business: Mapped["Business"] = relationship(
        "Business",
        back_populates="screenshots",
    )
    audit: Mapped[Optional["AuditReport"]] = relationship(
        "AuditReport",
        back_populates="screenshots",
    )

    def __repr__(self) -> str:
        return (
            f"<Screenshot id={self.id} business_id={self.business_id} "
            f"viewport={self.viewport.value!r}>"
        )
