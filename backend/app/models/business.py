from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.audit import AuditReport
    from app.models.contact import Contact
    from app.models.crm import Deal
    from app.models.proposal import Proposal
    from app.models.screenshot import Screenshot


class WebsiteStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    parked = "parked"
    abandoned = "abandoned"
    missing = "missing"


class Business(BaseModel):
    __tablename__ = "businesses"

    # ----- Core identity -----
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Classification -----
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ----- Location -----
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    state: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    zip_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    google_maps_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Contact -----
    phone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    phone2: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    whatsapp: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    email2: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    about_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    careers_page_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Website status -----
    has_website: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    website_status: Mapped[Optional[WebsiteStatus]] = mapped_column(
        Enum(WebsiteStatus, name="website_status_enum"),
        nullable=True,
        index=True,
    )

    # ----- Social media -----
    facebook_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instagram_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    twitter_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tiktok_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    youtube_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pinterest_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Social profiles (legacy JSON for backward compat) -----
    social_profiles: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Business details -----
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    review_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opening_hours: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    services: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(ARRAY(String), "postgresql"), nullable=True
    )
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    company_size: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Enrichment metadata -----
    completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    enrichment_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=True
    )
    last_enriched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Discovery provenance -----
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Timing -----
    discovered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_audited_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Scoring -----
    overall_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    opportunity_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    priority_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    revenue_potential: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ----- Stats -----
    audit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ----- Freeform -----
    tags: Mapped[Optional[List[str]]] = mapped_column(
        JSON().with_variant(ARRAY(String), "postgresql"),
        nullable=True,
    )
    metadata_: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )

    # ----- Relationships -----
    audits: Mapped[List["AuditReport"]] = relationship(
        "AuditReport",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    screenshots: Mapped[List["Screenshot"]] = relationship(
        "Screenshot",
        back_populates="business",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    contacts: Mapped[List["Contact"]] = relationship(
        "Contact", back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )
    deals: Mapped[List["Deal"]] = relationship(
        "Deal", back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )
    proposals: Mapped[List["Proposal"]] = relationship(
        "Proposal", back_populates="business", cascade="all, delete-orphan", lazy="selectin"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "industry": self.industry,
            "category": self.category,
            "subcategory": self.subcategory,
            "country": self.country,
            "state": self.state,
            "city": self.city,
            "zip_code": self.zip_code,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "google_maps_url": self.google_maps_url,
            "phone": self.phone,
            "phone2": self.phone2,
            "whatsapp": self.whatsapp,
            "email": self.email,
            "email2": self.email2,
            "website_url": self.website_url,
            "contact_page_url": self.contact_page_url,
            "about_page_url": self.about_page_url,
            "careers_page_url": self.careers_page_url,
            "has_website": self.has_website,
            "website_status": self.website_status.value if self.website_status else None,
            "facebook_url": self.facebook_url,
            "instagram_url": self.instagram_url,
            "linkedin_url": self.linkedin_url,
            "twitter_url": self.twitter_url,
            "tiktok_url": self.tiktok_url,
            "youtube_url": self.youtube_url,
            "pinterest_url": self.pinterest_url,
            "social_profiles": self.social_profiles,
            "rating": self.rating,
            "review_count": self.review_count,
            "opening_hours": self.opening_hours,
            "services": self.services,
            "founded_year": self.founded_year,
            "company_size": self.company_size,
            "logo_url": self.logo_url,
            "completeness_score": self.completeness_score,
            "enrichment_data": self.enrichment_data,
            "last_enriched_at": self.last_enriched_at.isoformat() if self.last_enriched_at else None,
            "source": self.source,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None,
            "last_audited_at": self.last_audited_at.isoformat() if self.last_audited_at else None,
            "overall_score": self.overall_score,
            "opportunity_score": self.opportunity_score,
            "priority_score": self.priority_score,
            "revenue_potential": self.revenue_potential,
            "audit_count": self.audit_count,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<Business id={self.id} name={self.name!r} slug={self.slug!r}>"
