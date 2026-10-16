"""
Pydantic v2 schemas for authentication and user management.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """Payload for registering a new user."""

    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("username")
    @classmethod
    def _username_alphanumeric(cls, v: str) -> str:
        if not all(c.isalnum() or c in ("_", "-") for c in v):
            raise ValueError(
                "Username may only contain letters, numbers, underscores, and hyphens."
            )
        return v.lower()


class UserUpdate(BaseModel):
    """Payload for updating the current user's profile."""

    full_name: Optional[str] = Field(default=None, max_length=255)
    avatar_url: Optional[str] = Field(default=None)
    # email changes deliberately excluded — require separate verification flow


class UserResponse(BaseModel):
    """User data returned by API responses."""

    model_config = {"from_attributes": True}

    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_superuser: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Token / auth schemas
# ---------------------------------------------------------------------------


class Token(BaseModel):
    """A single JWT string."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Claims decoded from a JWT payload."""

    sub: str
    email: Optional[str] = None
    scopes: list[str] = []
    token_type: str = "access"


class TokenResponse(BaseModel):
    """Full token pair returned after login or token refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        description="Access-token lifetime in seconds."
    )


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Credentials for the login endpoint."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Body for the token-refresh endpoint."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Body for the change-password endpoint."""

    current_password: str
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _new_different(cls, v: str, info) -> str:
        if info.data.get("current_password") and v == info.data["current_password"]:
            raise ValueError("New password must differ from the current password.")
        return v
