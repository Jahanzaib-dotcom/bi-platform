from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class EmailTemplateCreate(BaseModel):
    name: str
    subject: str
    body_html: str
    body_text: Optional[str] = None
    template_type: str = "initial_outreach"
    industry_target: Optional[str] = None
    variables: Optional[List[str]] = None


class EmailTemplateUpdate(BaseModel):
    name: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    body_text: Optional[str] = None
    template_type: Optional[str] = None
    industry_target: Optional[str] = None
    variables: Optional[List[str]] = None
    is_active: Optional[bool] = None


class EmailTemplateResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    subject: str
    body_html: str
    body_text: Optional[str]
    template_type: str
    industry_target: Optional[str]
    variables: Optional[List[str]]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignCreate(BaseModel):
    name: str
    description: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    industry_filter: Optional[str] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    config: Optional[Dict[str, Any]] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template_id: Optional[uuid.UUID] = None
    industry_filter: Optional[str] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: Optional[str]
    template_id: Optional[uuid.UUID]
    status: str
    industry_filter: Optional[str]
    min_score: Optional[float]
    max_score: Optional[float]
    total_recipients: int
    sent_count: int
    opened_count: int
    clicked_count: int
    replied_count: int
    bounced_count: int
    scheduled_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerateOutreachRequest(BaseModel):
    business_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None
    template_type: str = "initial_outreach"
    sender_name: str = "Web Services Team"
    include_audit: bool = True


class GenerateLinkedInRequest(BaseModel):
    business_id: uuid.UUID
    contact_id: Optional[uuid.UUID] = None


class PersonalizedEmailResponse(BaseModel):
    subject: str
    body_html: str
    body_text: str
    variables_used: Dict[str, str]


class SendEmailRequest(BaseModel):
    business_id: uuid.UUID
    to_email: str
    subject: str
    body_html: str
    body_text: str = ""
    reply_to: str = ""


class SmtpConfigRequest(BaseModel):
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    smtp_from_name: str = "Web Services Team"
    smtp_from_email: str = ""
    smtp_use_tls: bool = True


class SmtpStatusResponse(BaseModel):
    configured: bool
    host: str
    port: int
    username: str
    from_name: str
    from_email: str
