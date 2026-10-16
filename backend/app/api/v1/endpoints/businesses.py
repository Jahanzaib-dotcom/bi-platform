"""
Business CRUD, search, and action endpoints.

Routes
------
GET    /businesses                  – paginated list with filters
GET    /businesses/search           – full-text search
GET    /businesses/export           – trigger async export job
GET    /businesses/{id}             – single business
POST   /businesses                  – manual create
PUT    /businesses/{id}             – update
DELETE /businesses/{id}             – delete
POST   /businesses/{id}/audit       – trigger single audit
GET    /businesses/{id}/audits      – list audits for a business
GET    /businesses/{id}/screenshots – list screenshots for a business
POST   /businesses/bulk-audit       – trigger bulk audit
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import BusinessNotFoundError, ConflictError
from app.core.security import oauth2_scheme, verify_token
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business, WebsiteStatus
from app.models.screenshot import Screenshot
from app.models.user import User

router = APIRouter(prefix="/businesses", tags=["businesses"])


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    err = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        token_data = verify_token(token, expected_type="access")
    except Exception:
        raise err
    result = await db.execute(select(User).where(User.id == uuid.UUID(token_data.sub)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise err
    return user

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class BusinessCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    industry: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    website_url: Optional[str] = None
    social_profiles: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None


class BusinessUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    industry: Optional[str] = Field(None, max_length=100)
    category: Optional[str] = Field(None, max_length=100)
    subcategory: Optional[str] = Field(None, max_length=100)
    country: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    zip_code: Optional[str] = Field(None, max_length=20)
    address: Optional[str] = None
    phone: Optional[str] = Field(None, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    website_url: Optional[str] = None
    social_profiles: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    website_status: Optional[WebsiteStatus] = None


class AuditTriggerRequest(BaseModel):
    capture_screenshots: bool = True
    run_ai_analysis: bool = True


class BulkAuditRequest(BaseModel):
    business_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    capture_screenshots: bool = True
    run_ai_analysis: bool = True


class ExportQueryParams(BaseModel):
    industry: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    has_website: Optional[bool] = None
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    format: str = Field("csv", pattern="^(csv|excel|pdf)$")
    limit: int = Field(10000, ge=1, le=100000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_slug(name: str) -> str:
    try:
        from python_slugify import slugify  # type: ignore
        base = slugify(name, max_length=200)
    except ImportError:
        import re
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    suffix = uuid.uuid4().hex[:8]
    return f"{base}-{suffix}" if base else suffix


def _business_to_dict(b: Business) -> Dict[str, Any]:
    return {
        "id": str(b.id),
        "name": b.name,
        "slug": b.slug,
        "description": b.description,
        "industry": b.industry,
        "category": b.category,
        "subcategory": b.subcategory,
        "country": b.country,
        "state": b.state,
        "city": b.city,
        "zip_code": b.zip_code,
        "address": b.address,
        "latitude": b.latitude,
        "longitude": b.longitude,
        "google_maps_url": b.google_maps_url,
        "phone": b.phone,
        "phone2": b.phone2,
        "whatsapp": b.whatsapp,
        "email": b.email,
        "email2": b.email2,
        "website_url": b.website_url,
        "contact_page_url": b.contact_page_url,
        "about_page_url": b.about_page_url,
        "careers_page_url": b.careers_page_url,
        "has_website": b.has_website,
        "website_status": b.website_status.value if b.website_status else None,
        "facebook_url": b.facebook_url,
        "instagram_url": b.instagram_url,
        "linkedin_url": b.linkedin_url,
        "twitter_url": b.twitter_url,
        "tiktok_url": b.tiktok_url,
        "youtube_url": b.youtube_url,
        "pinterest_url": b.pinterest_url,
        "social_profiles": b.social_profiles,
        "rating": b.rating,
        "review_count": b.review_count,
        "opening_hours": b.opening_hours,
        "services": b.services,
        "founded_year": b.founded_year,
        "company_size": b.company_size,
        "logo_url": b.logo_url,
        "completeness_score": b.completeness_score,
        "enrichment_data": b.enrichment_data,
        "last_enriched_at": b.last_enriched_at.isoformat() if b.last_enriched_at else None,
        "source": b.source,
        "source_id": b.source_id,
        "source_url": b.source_url,
        "discovered_at": b.discovered_at.isoformat() if b.discovered_at else None,
        "last_audited_at": b.last_audited_at.isoformat() if b.last_audited_at else None,
        "overall_score": b.overall_score,
        "opportunity_score": b.opportunity_score,
        "priority_score": b.priority_score,
        "revenue_potential": b.revenue_potential,
        "audit_count": b.audit_count,
        "tags": b.tags,
        "metadata": b.metadata_,
        "created_at": b.created_at.isoformat(),
        "updated_at": b.updated_at.isoformat(),
    }


def _audit_to_dict(a: AuditReport) -> Dict[str, Any]:
    return {
        "id": str(a.id),
        "business_id": str(a.business_id),
        "status": a.status.value,
        "website_url": a.website_url,
        "screenshot_desktop_url": a.screenshot_desktop_url,
        "screenshot_mobile_url": a.screenshot_mobile_url,
        "ui_score": a.ui_score,
        "ux_score": a.ux_score,
        "mobile_score": a.mobile_score,
        "seo_score": a.seo_score,
        "accessibility_score": a.accessibility_score,
        "speed_score": a.speed_score,
        "security_score": a.security_score,
        "branding_score": a.branding_score,
        "content_score": a.content_score,
        "conversion_score": a.conversion_score,
        "overall_score": a.overall_score,
        "recommendations": a.recommendations,
        "ai_analysis": a.ai_analysis,
        "tech_stack": a.tech_stack,
        "performance_metrics": a.performance_metrics,
        "seo_issues": a.seo_issues,
        "accessibility_issues": a.accessibility_issues,
        "broken_links": a.broken_links,
        "error_message": a.error_message,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat(),
    }


def _screenshot_to_dict(s: Screenshot) -> Dict[str, Any]:
    return {
        "id": str(s.id),
        "business_id": str(s.business_id),
        "audit_id": str(s.audit_id) if s.audit_id else None,
        "viewport": s.viewport.value,
        "file_url": s.file_url,
        "file_path": s.file_path,
        "file_size": s.file_size,
        "width": s.width,
        "height": s.height,
        "url": s.url,
        "captured_at": s.captured_at.isoformat() if s.captured_at else None,
        "created_at": s.created_at.isoformat(),
    }


async def _get_business_or_404(
    business_id: uuid.UUID, db: AsyncSession
) -> Business:
    stmt = select(Business).where(Business.id == business_id)
    row = await db.execute(stmt)
    business = row.scalar_one_or_none()
    if business is None:
        raise BusinessNotFoundError(business_id=str(business_id))
    return business


# ---------------------------------------------------------------------------
# GET /businesses  – paginated list
# ---------------------------------------------------------------------------


@router.get("", status_code=status.HTTP_200_OK)
async def list_businesses(
    industry: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    has_website: Optional[bool] = Query(None),
    job_id: Optional[uuid.UUID] = Query(None, description="Filter by Discovery Job/Round ID"),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    sort_by: Optional[str] = Query(None, description="Field to sort by: opportunity_score, overall_score, created_at"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return a paginated, filterable list of businesses."""
    stmt = select(Business)

    if job_id:
        from app.models.discovery_result import DiscoveryResult
        stmt = stmt.join(DiscoveryResult, DiscoveryResult.business_id == Business.id).where(DiscoveryResult.job_id == job_id).distinct()

    if industry:
        stmt = stmt.where(Business.industry == industry)
    if country:
        stmt = stmt.where(Business.country == country)
    if city:
        stmt = stmt.where(Business.city == city)
    if has_website is not None:
        if has_website:
            stmt = stmt.where(
                or_(
                    Business.has_website == True,
                    (Business.website_url.isnot(None)) & (Business.website_url != ""),
                )
            )
        else:
            stmt = stmt.where(
                Business.has_website == False,
                or_(Business.website_url.is_(None), Business.website_url == ""),
            )
    if min_score is not None:
        stmt = stmt.where(Business.overall_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(Business.overall_score <= max_score)

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_row = await db.execute(count_stmt)
    total = total_row.scalar_one()

    # Sort
    _sort_col_map = {
        "opportunity_score": Business.opportunity_score,
        "overall_score": Business.overall_score,
        "priority_score": Business.priority_score,
        "revenue_potential": Business.revenue_potential,
        "completeness_score": Business.completeness_score,
        "created_at": Business.created_at,
    }
    _sort_col = _sort_col_map.get(sort_by or "", Business.created_at)
    from sqlalchemy import nulls_last
    offset = (page - 1) * page_size
    stmt = stmt.order_by(nulls_last(_sort_col.desc())).offset(offset).limit(page_size)
    rows = await db.execute(stmt)
    businesses = rows.scalars().all()

    return {
        "items": [_business_to_dict(b) for b in businesses],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


# ---------------------------------------------------------------------------
# GET /businesses/search  – full-text search  (MUST come before /{id})
# ---------------------------------------------------------------------------


@router.get("/search", status_code=status.HTTP_200_OK)
async def search_businesses(
    q: str = Query(..., min_length=1, description="Search term"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Full-text search on business name, category, and city."""
    term = f"%{q}%"
    filter_clause = or_(
        Business.name.ilike(term),
        Business.category.ilike(term),
        Business.city.ilike(term),
        Business.industry.ilike(term),
    )

    count_stmt = select(func.count(Business.id)).where(filter_clause)
    total_row = await db.execute(count_stmt)
    total = total_row.scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        select(Business)
        .where(filter_clause)
        .order_by(Business.name)
        .offset(offset)
        .limit(page_size)
    )
    rows = await db.execute(stmt)
    businesses = rows.scalars().all()

    return {
        "query": q,
        "items": [_business_to_dict(b) for b in businesses],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


# ---------------------------------------------------------------------------
# GET /businesses/export  – trigger async export job  (MUST come before /{id})
# ---------------------------------------------------------------------------


@router.get("/export", status_code=status.HTTP_200_OK)
async def export_businesses(
    industry: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    city: Optional[str] = Query(None),
    has_website: Optional[bool] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Export businesses as CSV (inline, no Celery)."""
    import csv
    import io
    from pathlib import Path
    from fastapi.responses import StreamingResponse

    stmt = select(Business)
    if industry:
        stmt = stmt.where(Business.industry == industry)
    if country:
        stmt = stmt.where(Business.country == country)
    if city:
        stmt = stmt.where(Business.city == city)
    if has_website is not None:
        stmt = stmt.where(Business.has_website == has_website)
    if min_score is not None:
        stmt = stmt.where(Business.overall_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(Business.overall_score <= max_score)

    stmt = stmt.limit(10000)
    rows = await db.execute(stmt)
    businesses = rows.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "name", "industry", "city", "country", "website_url", "phone", "email", "overall_score", "discovered_at"])
    for b in businesses:
        writer.writerow([str(b.id), b.name, b.industry or "", b.city or "", b.country or "", b.website_url or "", b.phone or "", b.email or "", b.overall_score or "", b.discovered_at.isoformat() if b.discovered_at else ""])

    return {
        "count": len(businesses),
        "data": output.getvalue(),
        "format": "csv",
        "status": "done",
    }


# ---------------------------------------------------------------------------
# POST /businesses/bulk-audit  (MUST come before /{id})
# ---------------------------------------------------------------------------


@router.post("/bulk-audit", status_code=status.HTTP_202_ACCEPTED)
async def bulk_audit_businesses(
    payload: BulkAuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Queue audit tasks for multiple businesses at once (inline, no Celery)."""
    from app.api.v1.endpoints.audits import _run_audit_inline

    business_ids = [str(bid) for bid in payload.business_ids]
    audit_ids: list[str] = []

    for bid_str in business_ids:
        try:
            bid = uuid.UUID(bid_str)
            biz = await _get_business_or_404(bid, db)
            audit = AuditReport(
                business_id=bid,
                website_url=biz.website_url,
                status=AuditStatus.pending,
            )
            db.add(audit)
            await db.flush()
            audit_ids.append(str(audit.id))
            background_tasks.add_task(
                _run_audit_inline,
                str(audit.id),
                bid_str,
                biz.website_url or "",
            )
        except Exception:
            pass

    await db.commit()

    return {
        "business_ids": business_ids,
        "audit_ids": audit_ids,
        "count": len(audit_ids),
        "status": "queued",
    }


# ---------------------------------------------------------------------------
# GET /businesses/{id}
# ---------------------------------------------------------------------------


@router.get("/{business_id}", status_code=status.HTTP_200_OK)
async def get_business(
    business_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Retrieve a single business by ID."""
    business = await _get_business_or_404(business_id, db)
    return _business_to_dict(business)


# ---------------------------------------------------------------------------
# POST /businesses
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_business(
    payload: BusinessCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Manually create a new business record."""
    slug = _make_slug(payload.name)

    # Guard against slug collision (extremely unlikely but correct)
    existing = await db.execute(select(Business).where(Business.slug == slug))
    if existing.scalar_one_or_none():
        slug = _make_slug(payload.name)  # regenerate – different uuid suffix

    business = Business(
        name=payload.name,
        slug=slug,
        description=payload.description,
        industry=payload.industry,
        category=payload.category,
        subcategory=payload.subcategory,
        country=payload.country,
        state=payload.state,
        city=payload.city,
        zip_code=payload.zip_code,
        address=payload.address,
        phone=payload.phone,
        email=payload.email,
        website_url=payload.website_url,
        has_website=bool(payload.website_url),
        website_status=WebsiteStatus.active if payload.website_url else None,
        social_profiles=payload.social_profiles,
        tags=payload.tags,
        discovered_at=datetime.now(timezone.utc),
    )
    db.add(business)
    await db.flush()
    await db.commit()
    await db.refresh(business)
    return _business_to_dict(business)


# ---------------------------------------------------------------------------
# POST /businesses/bulk-import
# ---------------------------------------------------------------------------

class BulkImportItem(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    address: Optional[str] = None
    industry: Optional[str] = None
    website_url: Optional[str] = None
    description: Optional[str] = None

class BulkImportRequest(BaseModel):
    businesses: List[BulkImportItem] = Field(..., min_length=1, max_length=500)

@router.post("/bulk-import", status_code=status.HTTP_201_CREATED)
async def bulk_import_businesses(
    payload: BulkImportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Bulk import manually researched businesses."""
    created, skipped = 0, 0
    for item in payload.businesses:
        # Skip duplicates by name+city
        stmt = select(Business).where(Business.name == item.name)
        if item.city:
            stmt = stmt.where(Business.city == item.city)
        existing = await db.execute(stmt)
        if existing.scalar_one_or_none():
            skipped += 1
            continue
        business = Business(
            name=item.name,
            slug=_make_slug(item.name),
            email=item.email,
            phone=item.phone,
            city=item.city,
            country=item.country or "United States",
            address=item.address,
            industry=item.industry or "fitness",
            category=item.industry or "fitness",
            website_url=item.website_url,
            has_website=bool(item.website_url),
            description=item.description,
            source="manual",
            discovered_at=datetime.now(timezone.utc),
        )
        db.add(business)
        created += 1
    await db.commit()
    return {"created": created, "skipped": skipped, "total": len(payload.businesses)}


# ---------------------------------------------------------------------------
# PUT /businesses/{id}
# ---------------------------------------------------------------------------


@router.put("/{business_id}", status_code=status.HTTP_200_OK)
async def update_business(
    business_id: uuid.UUID,
    payload: BusinessUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Update an existing business record."""
    business = await _get_business_or_404(business_id, db)

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(business, field, value)

    # Sync has_website when website_url changes
    if "website_url" in update_data:
        business.has_website = bool(update_data["website_url"])
        if update_data["website_url"] and not business.website_status:
            business.website_status = WebsiteStatus.active

    await db.commit()
    await db.refresh(business)
    return _business_to_dict(business)


# ---------------------------------------------------------------------------
# Bulk Delete & Clear Leads
# ---------------------------------------------------------------------------

class BulkDeleteRequest(BaseModel):
    business_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=1000)


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
@router.delete("/bulk", status_code=status.HTTP_200_OK)
async def bulk_delete_businesses(
    payload: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Bulk delete multiple businesses and all associated records."""
    from sqlalchemy import delete
    from app.models.crm import Activity, Deal
    from app.models.audit import AuditReport
    from app.models.discovery_result import DiscoveryResult

    deleted_count = 0
    for bid in payload.business_ids:
        try:
            deal_ids_row = await db.execute(select(Deal.id).where(Deal.business_id == bid))
            deal_ids = deal_ids_row.scalars().all()
            if deal_ids:
                await db.execute(delete(Activity).where(Activity.deal_id.in_(deal_ids)))
                await db.execute(delete(Deal).where(Deal.id.in_(deal_ids)))

            await db.execute(delete(AuditReport).where(AuditReport.business_id == bid))
            await db.execute(delete(DiscoveryResult).where(DiscoveryResult.business_id == bid))
            await db.execute(delete(Business).where(Business.id == bid))
            deleted_count += 1
        except Exception:
            pass

    await db.commit()
    return {"deleted": deleted_count, "status": "success"}


@router.post("/clear-all", status_code=status.HTTP_200_OK)
@router.delete("/clear-all", status_code=status.HTTP_200_OK)
async def clear_all_businesses(
    has_website: Optional[bool] = Query(None),
    job_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Clear businesses (optionally filtered by has_website or job_id)."""
    from sqlalchemy import delete
    from app.models.crm import Activity, Deal
    from app.models.audit import AuditReport
    from app.models.discovery_result import DiscoveryResult

    stmt = select(Business.id)
    if job_id:
        stmt = stmt.join(DiscoveryResult, DiscoveryResult.business_id == Business.id).where(DiscoveryResult.job_id == job_id)
    if has_website is not None:
        if has_website:
            stmt = stmt.where(or_(Business.has_website == True, (Business.website_url.isnot(None)) & (Business.website_url != "")))
        else:
            stmt = stmt.where(Business.has_website == False, or_(Business.website_url.is_(None), Business.website_url == ""))

    rows = await db.execute(stmt)
    bids = rows.scalars().all()

    for bid in bids:
        try:
            deal_ids_row = await db.execute(select(Deal.id).where(Deal.business_id == bid))
            deal_ids = deal_ids_row.scalars().all()
            if deal_ids:
                await db.execute(delete(Activity).where(Activity.deal_id.in_(deal_ids)))
                await db.execute(delete(Deal).where(Deal.id.in_(deal_ids)))

            await db.execute(delete(AuditReport).where(AuditReport.business_id == bid))
            await db.execute(delete(DiscoveryResult).where(DiscoveryResult.business_id == bid))
            await db.execute(delete(Business).where(Business.id == bid))
        except Exception:
            pass

    await db.commit()
    return {"deleted": len(bids), "status": "success"}


# ---------------------------------------------------------------------------
# DELETE /businesses/{id}
# ---------------------------------------------------------------------------


@router.delete("/{business_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business(
    business_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> None:
    """Permanently delete a business and all related data (cascade)."""
    from sqlalchemy import delete
    from app.models.crm import Activity, Deal
    from app.models.audit import AuditReport
    from app.models.discovery_result import DiscoveryResult

    business = await _get_business_or_404(business_id, db)
    deal_ids_row = await db.execute(select(Deal.id).where(Deal.business_id == business_id))
    deal_ids = deal_ids_row.scalars().all()
    if deal_ids:
        await db.execute(delete(Activity).where(Activity.deal_id.in_(deal_ids)))
        await db.execute(delete(Deal).where(Deal.id.in_(deal_ids)))

    await db.execute(delete(AuditReport).where(AuditReport.business_id == business_id))
    await db.execute(delete(DiscoveryResult).where(DiscoveryResult.business_id == business_id))
    await db.delete(business)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /businesses/{id}/audit  – trigger single audit
# ---------------------------------------------------------------------------


@router.post("/{business_id}/audit", status_code=status.HTTP_202_ACCEPTED)
async def trigger_audit(
    business_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    payload: AuditTriggerRequest = AuditTriggerRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Trigger an asynchronous website audit for this business."""
    from app.api.v1.endpoints.audits import _run_audit_inline

    business = await _get_business_or_404(business_id, db)

    audit = AuditReport(
        business_id=business_id,
        website_url=business.website_url,
        status=AuditStatus.pending,
    )
    db.add(audit)
    await db.flush()
    await db.commit()
    await db.refresh(audit)

    url = business.website_url or ""
    background_tasks.add_task(
        _run_audit_inline,
        str(audit.id),
        str(business_id),
        url,
    )

    return {
        "audit_id": str(audit.id),
        "business_id": str(business_id),
        "status": "queued",
    }


# ---------------------------------------------------------------------------
# GET /businesses/{id}/audits
# ---------------------------------------------------------------------------


@router.get("/{business_id}/audits", status_code=status.HTTP_200_OK)
async def list_business_audits(
    business_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return all audit reports for a business, most recent first."""
    await _get_business_or_404(business_id, db)

    count_stmt = select(func.count(AuditReport.id)).where(
        AuditReport.business_id == business_id
    )
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        select(AuditReport)
        .where(AuditReport.business_id == business_id)
        .order_by(AuditReport.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = await db.execute(stmt)
    audits = rows.scalars().all()

    return {
        "business_id": str(business_id),
        "items": [_audit_to_dict(a) for a in audits],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


# ---------------------------------------------------------------------------
# GET /businesses/{id}/screenshots
# ---------------------------------------------------------------------------


@router.get("/{business_id}/screenshots", status_code=status.HTTP_200_OK)
async def list_business_screenshots(
    business_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return all screenshots captured for a business."""
    await _get_business_or_404(business_id, db)

    count_stmt = select(func.count(Screenshot.id)).where(
        Screenshot.business_id == business_id
    )
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        select(Screenshot)
        .where(Screenshot.business_id == business_id)
        .order_by(Screenshot.captured_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = await db.execute(stmt)
    screenshots = rows.scalars().all()

    return {
        "business_id": str(business_id),
        "items": [_screenshot_to_dict(s) for s in screenshots],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


@router.post("/{business_id}/enrich", status_code=status.HTTP_200_OK)
async def enrich_business_contacts(
    business_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Scrape the business website to extract email, phone, and social links."""
    business = await _get_business_or_404(business_id, db)
    url = business.website_url or ""
    if not url:
        raise HTTPException(status_code=400, detail="Business has no website URL to scrape")
    background_tasks.add_task(_enrich_contacts_inline, str(business_id), url)
    return {"status": "enriching", "business_id": str(business_id)}


async def _enrich_contacts_inline(business_id: str, url: str) -> None:
    import uuid as _uuid
    import httpx
    from app.core.database import AsyncSessionLocal
    from app.engines.contact.contact_extractor import ContactExtractor, EXCLUDED_EMAILS

    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers, verify=False) as client:
            resp = await client.get(url)
            html = resp.text
    except Exception:
        return

    extractor = ContactExtractor()
    contacts = extractor.extract_from_html(html, url)

    async with AsyncSessionLocal() as session:
        biz_stmt = select(Business).where(Business.id == _uuid.UUID(business_id))
        row = await session.execute(biz_stmt)
        biz = row.scalar_one_or_none()
        if not biz:
            return

        if not biz.email:
            for c in sorted(contacts, key=lambda x: x.confidence_score, reverse=True):
                if c.email:
                    local = c.email.split("@")[0].lower()
                    if local not in EXCLUDED_EMAILS:
                        biz.email = c.email
                        break
            if not biz.email:
                for c in contacts:
                    if c.email:
                        biz.email = c.email
                        break

        if not biz.phone:
            for c in contacts:
                if c.phone and c.phone.startswith("+"):
                    biz.phone = c.phone
                    break

        existing_socials = biz.social_profiles or {}
        for c in contacts:
            for platform, link in (c.social_profiles or {}).items():
                if platform not in existing_socials:
                    existing_socials[platform] = link
        if existing_socials:
            biz.social_profiles = existing_socials

        await session.commit()
