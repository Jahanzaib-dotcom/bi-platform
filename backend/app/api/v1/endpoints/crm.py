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
from app.models.crm import Activity, ActivityType, Deal, DealStage, Pipeline
from app.models.user import User
from app.schemas.crm import (
    ActivityCreate,
    ActivityResponse,
    DealCreate,
    DealResponse,
    DealUpdate,
    PipelineCreate,
    PipelineResponse,
    PipelineUpdate,
)

router = APIRouter(prefix="/crm", tags=["crm"])


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


# ─── Pipelines ────────────────────────────────────────────────────────────────

@router.get("/pipelines", response_model=List[PipelineResponse])
async def list_pipelines(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    result = await db.execute(select(Pipeline).where(Pipeline.user_id == current_user.id))
    return result.scalars().all()


@router.post("/pipelines", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
async def create_pipeline(
    body: PipelineCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    pipeline = Pipeline(user_id=current_user.id, **body.model_dump())
    db.add(pipeline)
    await db.flush()
    return pipeline


@router.get("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def get_pipeline(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Pipeline, pipeline_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return p


@router.put("/pipelines/{pipeline_id}", response_model=PipelineResponse)
async def update_pipeline(
    pipeline_id: uuid.UUID,
    body: PipelineUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Pipeline, pipeline_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(p, field, value)
    await db.flush()
    return p


@router.delete("/pipelines/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pipeline(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Pipeline, pipeline_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    await db.delete(p)


# ─── Deals ────────────────────────────────────────────────────────────────────

@router.get("/deals", response_model=List[DealResponse])
async def list_deals(
    pipeline_id: Optional[uuid.UUID] = Query(None),
    stage: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    q = select(Deal).where(Deal.user_id == current_user.id)
    if pipeline_id:
        q = q.where(Deal.pipeline_id == pipeline_id)
    if stage:
        q = q.where(Deal.stage == stage)
    q = q.offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/deals", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    body: DealCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    deal = Deal(user_id=current_user.id, **body.model_dump())
    db.add(deal)
    await db.flush()
    return deal


@router.get("/deals/{deal_id}", response_model=DealResponse)
async def get_deal(
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    d = await db.get(Deal, deal_id)
    if not d or d.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Deal not found")
    return d


@router.put("/deals/{deal_id}", response_model=DealResponse)
async def update_deal(
    deal_id: uuid.UUID,
    body: DealUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    d = await db.get(Deal, deal_id)
    if not d or d.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Deal not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(d, field, value)

    if body.stage in ("won", "lost"):
        d.closed_at = datetime.now(timezone.utc)

    await db.flush()
    return d


@router.delete("/deals/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_deal(
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    d = await db.get(Deal, deal_id)
    if not d or d.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Deal not found")
    await db.delete(d)


# ─── Activities ───────────────────────────────────────────────────────────────

@router.get("/deals/{deal_id}/activities", response_model=List[ActivityResponse])
async def list_activities(
    deal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    d = await db.get(Deal, deal_id)
    if not d or d.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Deal not found")

    result = await db.execute(select(Activity).where(Activity.deal_id == deal_id))
    return result.scalars().all()


@router.post("/deals/{deal_id}/activities", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def add_activity(
    deal_id: uuid.UUID,
    body: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    d = await db.get(Deal, deal_id)
    if not d or d.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Deal not found")

    activity = Activity(
        deal_id=deal_id,
        user_id=current_user.id,
        activity_type=body.activity_type,
        subject=body.subject,
        body=body.body,
        scheduled_at=body.scheduled_at,
    )
    db.add(activity)
    await db.flush()
    return activity


# ─── Pipeline stats ───────────────────────────────────────────────────────────

@router.get("/pipelines/{pipeline_id}/stats")
async def pipeline_stats(
    pipeline_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
):
    p = await db.get(Pipeline, pipeline_id)
    if not p or p.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Pipeline not found")

    result = await db.execute(select(Deal).where(Deal.pipeline_id == pipeline_id))
    deals = result.scalars().all()

    stage_breakdown: dict[str, dict] = {}
    total_value = 0.0
    for deal in deals:
        stage = deal.stage
        if stage not in stage_breakdown:
            stage_breakdown[stage] = {"count": 0, "value": 0.0}
        stage_breakdown[stage]["count"] += 1
        stage_breakdown[stage]["value"] += deal.value
        total_value += deal.value

    won = [d for d in deals if d.stage == "won"]
    lost = [d for d in deals if d.stage == "lost"]

    return {
        "pipeline_id": str(pipeline_id),
        "total_deals": len(deals),
        "total_value": total_value,
        "won_count": len(won),
        "won_value": sum(d.value for d in won),
        "lost_count": len(lost),
        "stage_breakdown": stage_breakdown,
    }
