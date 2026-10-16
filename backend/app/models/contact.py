from __future__ import annotations
import enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.business import Business


class ContactRole(str, enum.Enum):
    owner = "owner"
    manager = "manager"
    marketing = "marketing"
    technical = "technical"
    sales = "sales"
    general = "general"
    unknown = "unknown"


class ContactSource(str, enum.Enum):
    website = "website"
    social = "social"
    directory = "directory"
    enrichment = "enrichment"
    manual = "manual"


class Contact(BaseModel):
    __tablename__ = "contacts"

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[ContactRole] = mapped_column(
        Enum(ContactRole, name="contact_role_enum"), default=ContactRole.unknown, nullable=False
    )
    source: Mapped[ContactSource] = mapped_column(
        Enum(ContactSource, name="contact_source_enum"), default=ContactSource.website, nullable=False
    )
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    social_profiles: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata", JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )

    business: Mapped["Business"] = relationship("Business", back_populates="contacts")

    def __repr__(self) -> str:
        return f"<Contact id={self.id} name={self.full_name!r} email={self.email!r}>"
