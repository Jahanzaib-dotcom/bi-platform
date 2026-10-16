from __future__ import annotations
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.contact import Contact
    from app.models.user import User


class ProposalStatus(str, enum.Enum):
    draft = "draft"
    generated = "generated"
    sent = "sent"
    viewed = "viewed"
    accepted = "accepted"
    rejected = "rejected"
    expired = "expired"


class Proposal(BaseModel):
    __tablename__ = "proposals"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    audit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("audit_reports.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[ProposalStatus] = mapped_column(
        Enum(ProposalStatus, name="proposal_status_enum"), default=ProposalStatus.draft, nullable=False, index=True
    )
    executive_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    problems_identified: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    solutions_proposed: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    pricing: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    timeline: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    expected_roi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    total_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    html_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    business: Mapped["Business"] = relationship("Business", back_populates="proposals")
    contact: Mapped[Optional["Contact"]] = relationship("Contact")

    def __repr__(self) -> str:
        return f"<Proposal id={self.id} title={self.title!r} status={self.status}>"
