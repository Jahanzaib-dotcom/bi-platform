"""
Model registry — importing this module registers all ORM classes on the
shared ``Base.metadata`` so that ``init_db()`` can issue a single
``CREATE TABLE`` pass for every table.
"""

from app.models.audit import AuditReport, AuditStatus
from app.models.base import BaseModel
from app.models.business import Business, WebsiteStatus
from app.models.contact import Contact, ContactRole, ContactSource
from app.models.crm import Activity, ActivityType, Deal, DealStage, Pipeline
from app.models.discovery_job import DiscoveryJob, JobStatus
from app.models.discovery_result import DiscoveryResult, ResultStatus
from app.models.outreach import (
    Campaign,
    CampaignRecipient,
    CampaignStatus,
    EmailTemplate,
    OutreachSequence,
    RecipientStatus,
    TemplateType,
)
from app.models.proposal import Proposal, ProposalStatus
from app.models.screenshot import Screenshot, Viewport
from app.models.user import User

__all__ = [
    "BaseModel",
    # domain models
    "User",
    "Business",
    "WebsiteStatus",
    "AuditReport",
    "AuditStatus",
    "Contact",
    "ContactRole",
    "ContactSource",
    "Pipeline",
    "Deal",
    "DealStage",
    "Activity",
    "ActivityType",
    "Campaign",
    "CampaignRecipient",
    "CampaignStatus",
    "EmailTemplate",
    "OutreachSequence",
    "RecipientStatus",
    "TemplateType",
    "Proposal",
    "ProposalStatus",
    "DiscoveryJob",
    "JobStatus",
    "DiscoveryResult",
    "ResultStatus",
    "Screenshot",
    "Viewport",
]
