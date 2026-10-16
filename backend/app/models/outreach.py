from __future__ import annotations
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.business import Business
    from app.models.contact import Contact
    from app.models.user import User


class TemplateType(str, enum.Enum):
    initial_outreach = "initial_outreach"
    follow_up = "follow_up"
    proposal = "proposal"
    linkedin_message = "linkedin_message"
    custom = "custom"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"
    cancelled = "cancelled"


class RecipientStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    delivered = "delivered"
    opened = "opened"
    clicked = "clicked"
    replied = "replied"
    bounced = "bounced"
    unsubscribed = "unsubscribed"
    failed = "failed"


class EmailTemplate(BaseModel):
    __tablename__ = "email_templates"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body_html: Mapped[str] = mapped_column(Text, nullable=False)
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_type: Mapped[TemplateType] = mapped_column(
        Enum(TemplateType, name="template_type_enum"), default=TemplateType.initial_outreach, nullable=False
    )
    industry_target: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    variables: Mapped[Optional[List[str]]] = mapped_column(JSON(), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<EmailTemplate id={self.id} name={self.name!r}>"


class Campaign(BaseModel):
    __tablename__ = "outreach_campaigns"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("email_templates.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status_enum"), default=CampaignStatus.draft, nullable=False, index=True
    )
    industry_filter: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    min_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_recipients: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sent_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opened_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicked_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    replied_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bounced_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    template: Mapped[Optional["EmailTemplate"]] = relationship("EmailTemplate")
    recipients: Mapped[List["CampaignRecipient"]] = relationship(
        "CampaignRecipient", back_populates="campaign", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Campaign id={self.id} name={self.name!r} status={self.status}>"


class CampaignRecipient(BaseModel):
    __tablename__ = "campaign_recipients"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("outreach_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RecipientStatus] = mapped_column(
        Enum(RecipientStatus, name="recipient_status_enum"), default=RecipientStatus.pending, nullable=False, index=True
    )
    personalized_subject: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    personalized_body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    clicked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    bounce_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="recipients")

    def __repr__(self) -> str:
        return f"<CampaignRecipient id={self.id} email={self.email!r} status={self.status}>"


class OutreachSequence(BaseModel):
    __tablename__ = "outreach_sequences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    steps: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    # steps schema: [{delay_days: int, template_id: uuid, channel: "email"|"linkedin"}]
    total_enrolled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_converted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<OutreachSequence id={self.id} name={self.name!r}>"
