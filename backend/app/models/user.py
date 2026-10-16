from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.discovery_job import DiscoveryJob


class User(BaseModel):
    __tablename__ = "users"

    # ----- Identity -----
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)

    # ----- Profile -----
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ----- Flags -----
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ----- API access -----
    api_key: Mapped[Optional[str]] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=True,
        default=lambda: secrets.token_urlsafe(48),
    )

    # ----- Activity -----
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ----- Relationships -----
    discovery_jobs: Mapped[List["DiscoveryJob"]] = relationship(
        "DiscoveryJob",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
