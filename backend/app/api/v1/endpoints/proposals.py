from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationError
from app.core.security import oauth2_scheme, verify_token
from app.engines.proposal.proposal_generator import ProposalGenerator
from app.models.audit import AuditReport
from app.models.business import Business
from app.models.contact import Contact
from app.models.proposal import Proposal, ProposalStatus
from app.models.user import User
from app.schemas.proposal import ProposalGenerateRequest, ProposalResponse, ProposalUpdate

router = APIRouter(prefix="/proposals", tags=["proposals"])
_generator = ProposalGenerator()


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


@router.get("", response_model=List[ProposalResponse])
async def list_proposals(
    business_id: Optional[uuid.UUID] = Query(None),
    proposal_status: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = select(Proposal).where(Proposal.user_id == current_user.id)
    if business_id:
        q = q.where(Proposal.business_id == business_id)
    if proposal_status:
        q = q.where(Proposal.status == proposal_status)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/generate", response_model=ProposalResponse, status_code=status.HTTP_201_CREATED)
async def generate_proposal(
    body: ProposalGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    biz = await db.get(Business, body.business_id)
    if not biz:
        raise HTTPException(status_code=404, detail="Business not found")

    business_data = biz.to_dict()

    audit_data = None
    audit_id = body.audit_id
    if audit_id:
        audit = await db.get(AuditReport, audit_id)
        if audit:
            audit_data = audit.to_dict()
    else:
        q = (
            select(AuditReport)
            .where(AuditReport.business_id == body.business_id)
            .order_by(AuditReport.created_at.desc())
            .limit(1)
        )
        result = await db.execute(q)
        latest = result.scalar_one_or_none()
        if latest:
            audit_id = latest.id
            audit_data = latest.to_dict()

    contact_data = None
    if body.contact_id:
        contact = await db.get(Contact, body.contact_id)
        if contact:
            contact_data = contact.to_dict()

    generated = _generator.generate(
        business_data=business_data,
        audit_data=audit_data,
        contact_data=contact_data,
        custom_services=body.custom_services,
    )

    html_content = _generator.generate_html(generated, business_data)

    proposal = Proposal(
        business_id=body.business_id,
        contact_id=body.contact_id,
        user_id=current_user.id,
        audit_id=audit_id,
        title=generated.title,
        status=ProposalStatus.generated,
        executive_summary=generated.executive_summary,
        problems_identified=[
            {
                "title": p.title,
                "description": p.description,
                "impact": p.impact,
                "severity": p.severity,
            }
            for p in generated.problems
        ],
        solutions_proposed=[
            {
                "title": s.title,
                "description": s.description,
                "deliverables": s.deliverables,
                "timeline_weeks": s.timeline_weeks,
                "price_min": s.price_min,
                "price_max": s.price_max,
                "recurring": s.recurring,
                "period": s.period,
            }
            for s in generated.solutions
        ],
        pricing=generated.pricing,
        timeline=generated.timeline,
        expected_roi=generated.expected_roi,
        total_value=(generated.total_value_min + generated.total_value_max) / 2,
        valid_until=generated.valid_until,
        html_content=html_content,
    )

    db.add(proposal)
    await db.flush()
    return proposal


@router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Proposal, proposal_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return p


@router.get("/{proposal_id}/html")
async def get_proposal_html(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    from fastapi.responses import HTMLResponse
    p = await db.get(Proposal, proposal_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if not p.html_content:
        raise HTTPException(status_code=404, detail="HTML content not available")
    return HTMLResponse(content=p.html_content)


@router.put("/{proposal_id}", response_model=ProposalResponse)
async def update_proposal(
    proposal_id: uuid.UUID,
    body: ProposalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Proposal, proposal_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    await db.flush()
    return p


@router.post("/{proposal_id}/send")
async def mark_sent(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Proposal, proposal_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    p.status = ProposalStatus.sent
    p.sent_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "sent", "proposal_id": str(proposal_id)}


@router.delete("/{proposal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_proposal(
    proposal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Proposal, proposal_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    await db.delete(p)
