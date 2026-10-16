from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PipelineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_default: bool = False
    stages_config: Optional[Dict[str, Any]] = None


class PipelineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_default: Optional[bool] = None
    stages_config: Optional[Dict[str, Any]] = None


class PipelineResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    is_default: bool
    stages_config: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    business_id: uuid.UUID
    pipeline_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    title: str
    stage: str = "lead"
    value: float = 0.0
    currency: str = "USD"
    probability: float = 0.0
    expected_close_date: Optional[datetime] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class DealUpdate(BaseModel):
    title: Optional[str] = None
    stage: Optional[str] = None
    value: Optional[float] = None
    probability: Optional[float] = None
    expected_close_date: Optional[datetime] = None
    notes: Optional[str] = None
    lost_reason: Optional[str] = None
    tags: Optional[List[str]] = None


class DealResponse(BaseModel):
    id: uuid.UUID
    business_id: uuid.UUID
    pipeline_id: uuid.UUID
    contact_id: Optional[uuid.UUID]
    user_id: uuid.UUID
    title: str
    stage: str
    value: float
    currency: str
    probability: float
    expected_close_date: Optional[datetime]
    closed_at: Optional[datetime]
    lost_reason: Optional[str]
    notes: Optional[str]
    tags: Optional[List[str]]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActivityCreate(BaseModel):
    deal_id: uuid.UUID
    activity_type: str
    subject: Optional[str] = None
    body: Optional[str] = None
    scheduled_at: Optional[datetime] = None


class ActivityResponse(BaseModel):
    id: uuid.UUID
    deal_id: uuid.UUID
    user_id: uuid.UUID
    activity_type: str
    subject: Optional[str]
    body: Optional[str]
    scheduled_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
