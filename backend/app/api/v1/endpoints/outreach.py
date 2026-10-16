from __future__ import annotations

import uuid
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import oauth2_scheme, verify_token
from app.engines.outreach.campaign_manager import CampaignManager
from app.engines.outreach.email_personalizer import EmailPersonalizer
from app.models.audit import AuditReport
from app.models.business import Business
from app.models.contact import Contact
from app.models.outreach import Campaign, CampaignStatus, EmailTemplate
from app.models.user import User
from app.schemas.outreach import (
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
    GenerateLinkedInRequest,
    GenerateOutreachRequest,
    PersonalizedEmailResponse,
    SendEmailRequest,
    SmtpConfigRequest,
    SmtpStatusResponse,
)

router = APIRouter(prefix="/outreach", tags=["outreach"])
_personalizer = EmailPersonalizer()


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    err = HTTPException(status_code=401, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        token_data = verify_token(token, expected_type="access")
    except AuthenticationError:
        raise err
    result = await db.execute(select(User).where(User.id == uuid.UUID(token_data.sub)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise err
    return user


# ─── Email Templates ──────────────────────────────────────────────────────────

@router.get("/templates", response_model=List[EmailTemplateResponse])
async def list_templates(
    industry: Optional[str] = Query(None),
    template_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = select(EmailTemplate).where(EmailTemplate.user_id == current_user.id)
    if industry:
        q = q.where(EmailTemplate.industry_target == industry)
    if template_type:
        q = q.where(EmailTemplate.template_type == template_type)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/templates", response_model=EmailTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    template = EmailTemplate(user_id=current_user.id, **body.model_dump())
    db.add(template)
    await db.flush()
    return template


@router.get("/templates/{template_id}", response_model=EmailTemplateResponse)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    t = await db.get(EmailTemplate, template_id)
    if not t or t.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    body: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    t = await db.get(EmailTemplate, template_id)
    if not t or t.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(t, field, value)
    await db.flush()
    return t


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    t = await db.get(EmailTemplate, template_id)
    if not t or t.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(t)


# ─── Campaigns ────────────────────────────────────────────────────────────────

@router.get("/campaigns", response_model=List[CampaignResponse])
async def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = select(Campaign).where(Campaign.user_id == current_user.id)
    if status_filter:
        q = q.where(Campaign.status == status_filter)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    mgr = CampaignManager(db)
    data = await mgr.create_campaign(
        user_id=current_user.id,
        name=body.name,
        template_id=body.template_id,
        industry_filter=body.industry_filter,
        min_score=body.min_score,
        max_score=body.max_score,
        description=body.description,
    )
    campaign = await db.get(Campaign, uuid.UUID(data["id"]))
    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return c


@router.put("/campaigns/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(c, field, value)
    await db.flush()
    return c


@router.post("/campaigns/{campaign_id}/start")
async def start_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    mgr = CampaignManager(db)
    data = await mgr.start_campaign(campaign_id)
    return {"status": "started", "campaign_id": str(campaign_id)}


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    mgr = CampaignManager(db)
    await mgr.pause_campaign(campaign_id)
    return {"status": "paused", "campaign_id": str(campaign_id)}


@router.get("/campaigns/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    c = await db.get(Campaign, campaign_id)
    if not c or c.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Campaign not found")
    mgr = CampaignManager(db)
    return await mgr.get_campaign_stats(campaign_id)


# ─── Email generation ─────────────────────────────────────────────────────────

@router.post("/generate", response_model=PersonalizedEmailResponse)
async def generate_outreach_email(
    body: GenerateOutreachRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    biz = await db.get(Business, body.business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    business_data = biz.to_dict()

    audit_data = None
    if body.include_audit:
        q = (
            select(AuditReport)
            .where(AuditReport.business_id == body.business_id)
            .order_by(AuditReport.created_at.desc())
            .limit(1)
        )
        result = await db.execute(q)
        audit = result.scalar_one_or_none()
        if audit:
            audit_data = audit.to_dict()

    contact_data = None
    if body.contact_id:
        contact = await db.get(Contact, body.contact_id)
        if contact:
            contact_data = contact.to_dict()

    if body.template_type == "initial_outreach":
        email = _personalizer.generate_outreach_email(
            business_data=business_data,
            audit_data=audit_data,
            contact_data=contact_data,
            sender_name=body.sender_name,
        )
    else:
        follow_up_num = {"follow_up_1": 1, "follow_up_2": 2}.get(body.template_type, 1)
        email = _personalizer.generate_follow_up(
            business_data=business_data,
            follow_up_number=follow_up_num,
            contact_data=contact_data,
            sender_name=body.sender_name,
        )

    return PersonalizedEmailResponse(
        subject=email.subject,
        body_html=email.body_html,
        body_text=email.body_text,
        variables_used=email.variables_used,
    )


@router.post("/generate-linkedin")
async def generate_linkedin_message(
    body: GenerateLinkedInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    biz = await db.get(Business, body.business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    business_data = biz.to_dict()
    contact_data = None
    if body.contact_id:
        contact = await db.get(Contact, body.contact_id)
        if contact:
            contact_data = contact.to_dict()

    message = _personalizer.generate_linkedin_message(business_data, contact_data)
    return {"message": message}


# ─── SMTP / Email Sending ─────────────────────────────────────────────────────

@router.get("/smtp-status", response_model=SmtpStatusResponse)
async def get_smtp_status(current_user: User = Depends(_get_current_user)):
    from app.core.config import settings
    return SmtpStatusResponse(
        configured=bool(settings.SMTP_USERNAME and settings.SMTP_PASSWORD),
        host=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME,
        from_name=settings.SMTP_FROM_NAME,
        from_email=settings.SMTP_FROM_EMAIL or settings.SMTP_USERNAME,
    )


@router.post("/smtp-config")
async def update_smtp_config(
    body: SmtpConfigRequest,
    current_user: User = Depends(_get_current_user),
):
    """Persist SMTP credentials to the .env file."""
    import os
    from pathlib import Path

    env_path = Path(__file__).parent.parent.parent.parent.parent / ".env"
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    existing["SMTP_HOST"] = body.smtp_host
    existing["SMTP_PORT"] = str(body.smtp_port)
    existing["SMTP_USERNAME"] = body.smtp_username
    existing["SMTP_PASSWORD"] = body.smtp_password
    existing["SMTP_FROM_NAME"] = body.smtp_from_name
    existing["SMTP_FROM_EMAIL"] = body.smtp_from_email or body.smtp_username
    # Update environment variables in running process
    os.environ["SMTP_HOST"] = body.smtp_host
    os.environ["SMTP_PORT"] = str(body.smtp_port)
    os.environ["SMTP_USERNAME"] = body.smtp_username
    os.environ["SMTP_PASSWORD"] = body.smtp_password
    os.environ["SMTP_FROM_NAME"] = body.smtp_from_name
    os.environ["SMTP_FROM_EMAIL"] = body.smtp_from_email or body.smtp_username
    os.environ["SMTP_USE_TLS"] = "true" if body.smtp_use_tls else "false"

    # Update in-memory settings singleton directly
    try:
        from app.core.config import settings, load_settings
        settings.SMTP_HOST = body.smtp_host
        settings.SMTP_PORT = body.smtp_port
        settings.SMTP_USERNAME = body.smtp_username
        settings.SMTP_PASSWORD = body.smtp_password
        settings.SMTP_FROM_NAME = body.smtp_from_name
        settings.SMTP_FROM_EMAIL = body.smtp_from_email or body.smtp_username
        settings.SMTP_USE_TLS = body.smtp_use_tls
        load_settings.cache_clear()
    except Exception:
        pass

    try:
        env_path.write_text("\n".join(f"{k}={v}" for k, v in existing.items()) + "\n")
    except OSError as err:
        logger.warning("Could not persist SMTP config to .env (read-only filesystem): %s", err)

    return {"status": "saved", "message": "SMTP configuration saved and activated immediately."}


@router.post("/smtp-test")
async def test_smtp(current_user: User = Depends(_get_current_user)):
    from app.services.email_sender import test_smtp_connection
    result = await test_smtp_connection()
    if result.success:
        return {"status": "ok", "message": "SMTP connection successful"}
    raise HTTPException(status_code=400, detail=f"SMTP connection failed: {result.error}")


@router.post("/send")
async def send_outreach_email(
    body: SendEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    from app.services.outreach_provider import get_outreach_provider

    provider = get_outreach_provider()
    try:
        result = await provider.send(
            to_email=body.to_email,
            subject=body.subject,
            body_html=body.body_html,
            body_text=body.body_text,
            reply_to=body.reply_to,
        )
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return {"status": "sent", "to": body.to_email, "subject": body.subject, "provider": result.provider}
