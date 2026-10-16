"""
Freelance client & hiring project discovery endpoints.

Routes
------
GET  /freelance/live-jobs    – Search live jobs across Upwork, Freelancer.com, and Fiverr with AI proposals
POST /freelance/save-to-crm  – Save a freelance project to CRM leads & sales pipeline
GET  /freelance/saved-leads  – List all saved freelance clients from database
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import oauth2_scheme, verify_token
from app.engines.discovery.providers.freelance_provider import (
    FreelanceProvider,
    generate_freelance_proposal,
)
from app.models.business import Business, WebsiteStatus
from app.models.crm import Deal, DealStage, Pipeline
from app.models.user import User

router = APIRouter(prefix="/freelance", tags=["freelance"])


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token_data = verify_token(token, expected_type="access")
    except Exception:
        raise err
    result = await db.execute(select(User).where(User.id == uuid.UUID(token_data.sub)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise err
    return user


class SaveFreelanceJobRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    platform: str = Field(..., max_length=50)
    project_url: str = Field(..., max_length=1000)
    budget: Optional[str] = None
    description: Optional[str] = None
    pitch: Optional[str] = None
    category: Optional[str] = "Web Development & E-Commerce"


@router.get("/live-jobs", status_code=status.HTTP_200_OK)
async def search_live_jobs(
    query: str = Query("website design", min_length=1, max_length=200),
    platform: Optional[str] = Query(None, description="all, upwork, freelancer, or fiverr"),
    limit: int = Query(25, ge=1, le=100),
    current_user: User = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Search active paying clients and hiring projects live from
    Freelancer.com, Upwork, and Fiverr.
    Each job includes an AI-crafted proposal ready to submit.
    """
    provider = FreelanceProvider()
    clean_query = query.strip()
    target_platform = (platform or "all").lower()

    results: List[Dict[str, Any]] = []

    # 1. Freelancer.com API
    if target_platform in ("all", "freelancer"):
        fl_items = await provider._fetch_freelancer_api(clean_query, max_results=min(limit, 30))
        for item in fl_items:
            raw = item.raw_data
            results.append({
                "id": str(uuid.uuid4()),
                "title": item.name.replace("Client: ", ""),
                "platform": "freelancer",
                "platform_name": "Freelancer.com",
                "project_url": raw.get("project_url"),
                "budget": raw.get("budget"),
                "description": raw.get("job_description") or "Client is actively seeking a web designer/developer for this project.",
                "pitch": raw.get("pitch") or generate_freelance_proposal(
                    title=item.name,
                    description=raw.get("job_description", ""),
                    platform="Freelancer.com",
                    budget=raw.get("budget"),
                ),
                "source_id": item.source_id,
            })

    # 2. Upwork live search
    if target_platform in ("all", "upwork") and len(results) < limit:
        uw_items = await provider._search_upwork_jobs(clean_query, max_results=min(limit - len(results), 20))
        for item in uw_items:
            raw = item.raw_data
            results.append({
                "id": str(uuid.uuid4()),
                "title": item.name.replace("Client: ", ""),
                "platform": "upwork",
                "platform_name": "Upwork",
                "project_url": raw.get("project_url"),
                "budget": raw.get("budget"),
                "description": raw.get("job_description") or "Live Upwork job posting for website development.",
                "pitch": raw.get("pitch") or generate_freelance_proposal(
                    title=item.name,
                    description=raw.get("job_description", ""),
                    platform="Upwork",
                    budget=raw.get("budget"),
                ),
                "source_id": item.source_id,
            })

    # 3. Fiverr buyer requests / searches
    if target_platform in ("all", "fiverr") and len(results) < limit:
        fv_items = await provider._search_fiverr_jobs(clean_query, max_results=min(limit - len(results), 15))
        for item in fv_items:
            raw = item.raw_data
            results.append({
                "id": str(uuid.uuid4()),
                "title": item.name.replace("Client: ", ""),
                "platform": "fiverr",
                "platform_name": "Fiverr",
                "project_url": raw.get("project_url"),
                "budget": raw.get("budget"),
                "description": raw.get("job_description") or "Live Fiverr client request for web services.",
                "pitch": raw.get("pitch") or generate_freelance_proposal(
                    title=item.name,
                    description=raw.get("job_description", ""),
                    platform="Fiverr",
                ),
                "source_id": item.source_id,
            })

    return {
        "items": results[:limit],
        "total": len(results[:limit]),
        "query": clean_query,
        "platform": target_platform,
    }


@router.post("/save-to-crm", status_code=status.HTTP_201_CREATED)
async def save_job_to_crm(
    body: SaveFreelanceJobRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Save a discovered freelance job into the CRM Leads & Deals pipeline.
    """
    # Dedup by project_url or title
    check_stmt = select(Business).where(
        (Business.source_url == body.project_url) | (Business.name == f"Client: {body.title}")
    )
    existing = (await db.execute(check_stmt)).scalars().first()

    if existing:
        return {
            "message": "Lead already saved in CRM",
            "business_id": str(existing.id),
            "status": "existing",
        }

    # Ensure user has a default sales pipeline
    pipe_stmt = (
        select(Pipeline)
        .where(Pipeline.user_id == current_user.id)
        .order_by(Pipeline.is_default.desc())
    )
    pipe_row = await db.execute(pipe_stmt)
    user_pipeline = pipe_row.scalars().first()
    if not user_pipeline:
        user_pipeline = Pipeline(
            user_id=current_user.id,
            name="Freelance Clients & Projects",
            description="Active hiring clients from Upwork, Freelancer.com, and Fiverr",
            is_default=True,
        )
        db.add(user_pipeline)
        await db.flush()

    # Parse estimated deal value from budget
    est_value = 1500.0
    if body.budget:
        import re
        nums = [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d+)*", body.budget)]
        if nums:
            est_value = max(nums)

    slug_base = f"{body.platform}-{uuid.uuid4().hex[:8]}"

    new_biz = Business(
        name=f"Client: {body.title}",
        slug=slug_base,
        category=body.category or "Freelance / Web Project",
        industry="Web Development & Design",
        country="Global",
        city="Remote",
        has_website=False,
        website_status=None,
        description=body.description,
        source=body.platform.lower(),
        source_id=body.project_url,
        source_url=body.project_url,
        discovered_at=datetime.now(timezone.utc),
        opportunity_score=92.0,
        priority_score=90.0,
        revenue_potential=est_value,
        metadata_={
            "platform": body.platform,
            "project_url": body.project_url,
            "budget": body.budget,
            "pitch": body.pitch,
            "raw_source": {
                "platform": body.platform,
                "project_url": body.project_url,
                "budget": body.budget,
                "pitch": body.pitch,
                "job_description": body.description,
            },
        },
    )
    db.add(new_biz)
    await db.flush()

    new_deal = Deal(
        business_id=new_biz.id,
        pipeline_id=user_pipeline.id,
        user_id=current_user.id,
        title=f"{body.platform.title()} Project: {body.title[:60]}",
        stage=DealStage.lead,
        value=est_value,
        currency="USD",
        probability=0.35,
        notes=f"Discovered via {body.platform.title()}. Budget: {body.budget or 'TBD'}. Job link: {body.project_url}",
    )
    db.add(new_deal)
    await db.commit()

    return {
        "message": "Project successfully saved to CRM Leads & Deals pipeline",
        "business_id": str(new_biz.id),
        "deal_id": str(new_deal.id),
        "status": "created",
    }


@router.get("/saved-leads", status_code=status.HTTP_200_OK)
async def list_saved_freelance_leads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    List all freelance leads saved in the user's CRM.
    """
    stmt = (
        select(Business)
        .where(
            Business.source.in_(["freelance", "upwork", "freelancer", "fiverr"])
        )
        .order_by(Business.discovered_at.desc())
    )
    rows = await db.execute(stmt)
    businesses = rows.scalars().all()

    items = []
    for b in businesses:
        meta = b.metadata_ or {}
        items.append({
            "id": str(b.id),
            "name": b.name,
            "source": b.source,
            "source_url": b.source_url or meta.get("project_url"),
            "budget": meta.get("budget"),
            "pitch": meta.get("pitch"),
            "description": b.description,
            "discovered_at": b.discovered_at.isoformat() if b.discovered_at else None,
            "opportunity_score": b.opportunity_score,
            "revenue_potential": b.revenue_potential,
        })

    return {"items": items, "total": len(items)}
