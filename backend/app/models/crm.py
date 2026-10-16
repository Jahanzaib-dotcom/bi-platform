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


class DealStage(str, enum.Enum):
    lead = "lead"
    contacted = "contacted"
    qualified = "qualified"
    proposal_sent = "proposal_sent"
    negotiation = "negotiation"
    won = "won"
    lost = "lost"


class ActivityType(str, enum.Enum):
    note = "note"
    email_sent = "email_sent"
    email_received = "email_received"
    call = "call"
    meeting = "meeting"
    proposal = "proposal"
    follow_up = "follow_up"
    status_change = "status_change"


class Pipeline(BaseModel):
    __tablename__ = "crm_pipelines"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    stages_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    deals: Mapped[List["Deal"]] = relationship("Deal", back_populates="pipeline", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Pipeline id={self.id} name={self.name!r}>"


class Deal(BaseModel):
    __tablename__ = "crm_deals"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[DealStage] = mapped_column(
        Enum(DealStage, name="deal_stage_enum"), default=DealStage.lead, nullable=False, index=True
    )
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    expected_close_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON(), nullable=True)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    business: Mapped["Business"] = relationship("Business", back_populates="deals")
    pipeline: Mapped["Pipeline"] = relationship("Pipeline", back_populates="deals")
    contact: Mapped[Optional["Contact"]] = relationship("Contact")
    activities: Mapped[List["Activity"]] = relationship("Activity", back_populates="deal", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Deal id={self.id} title={self.title!r} stage={self.stage}>"


class Activity(BaseModel):
    __tablename__ = "crm_activities"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_type: Mapped[ActivityType] = mapped_column(
        Enum(ActivityType, name="activity_type_enum"), nullable=False, index=True
    )
    subject: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    deal: Mapped["Deal"] = relationship("Deal", back_populates="activities")

    def __repr__(self) -> str:
        return f"<Activity id={self.id} type={self.activity_type}>"
