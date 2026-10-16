from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, field_validator


class ContactBase(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    role: str = "unknown"
    source: str = "website"
    linkedin_url: Optional[str] = None
    is_primary: bool = False
    social_profiles: Optional[Dict[str, Any]] = None


class ContactCreate(ContactBase):
    business_id: uuid.UUID


class ContactUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    role: Optional[str] = None
    linkedin_url: Optional[str] = None
    is_primary: Optional[bool] = None
    social_profiles: Optional[Dict[str, Any]] = None


class ContactResponse(ContactBase):
    id: uuid.UUID
    business_id: uuid.UUID
    email_verified: bool
    confidence_score: float
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactExtractRequest(BaseModel):
    business_id: uuid.UUID
    url: str
    html: Optional[str] = None


class EmailPatternRequest(BaseModel):
    first_name: str
    last_name: str
    domain: str
