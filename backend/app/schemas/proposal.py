from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ProposalGenerateRequest(BaseModel):
    business_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    audit_id: Optional[uuid.UUID] = None
    custom_services: Optional[List[str]] = None


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    executive_summary: Optional[str] = None
    pricing: Optional[Dict[str, Any]] = None
    valid_until: Optional[datetime] = None


class ProposalResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    contact_id: Optional[uuid.UUID]
    user_id: uuid.UUID
    audit_id: Optional[uuid.UUID]
    title: str
    status: str
    executive_summary: Optional[str]
    problems_identified: Optional[List[Dict[str, Any]]]
    solutions_proposed: Optional[List[Dict[str, Any]]]
    pricing: Optional[Dict[str, Any]]
    timeline: Optional[Dict[str, Any]]
    expected_roi: Optional[str]
    total_value: float
    valid_until: Optional[datetime]
    sent_at: Optional[datetime]
    viewed_at: Optional[datetime]
    responded_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
