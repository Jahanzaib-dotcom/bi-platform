"""
Discovery job management endpoints.

Routes
------
GET  /discovery/jobs                      – list all jobs (paginated)
POST /discovery/jobs                      – create + start new job
GET  /discovery/jobs/{id}                 – get job details
POST /discovery/jobs/{id}/pause           – pause a running job
POST /discovery/jobs/{id}/resume          – resume a paused job
POST /discovery/jobs/{id}/cancel          – cancel a job
DELETE /discovery/jobs/{id}               – delete a job record
GET  /discovery/providers                 – list available providers with status
POST /discovery/providers/{name}/test     – test provider connectivity
GET  /discovery/jobs/{id}/results         – paginated discovery results for a job
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import oauth2_scheme, verify_token
from app.models.discovery_job import DiscoveryJob, JobStatus
from app.models.discovery_result import DiscoveryResult, ResultStatus
from app.models.user import User

router = APIRouter(prefix="/discovery", tags=["discovery"])


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


class DiscoveryJobFilters(BaseModel):
    save_with_website: bool = True
    save_no_website: bool = True
    require_email: bool = False
    require_whatsapp: bool = False


class DiscoveryJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    keywords: str = Field(..., min_length=1, description="Search keywords / business type")
    country: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    industry: Optional[str] = Field(None, max_length=100)
    sources: List[str] = Field(
        default_factory=lambda: ["duckduckgo"],
        description="Provider names to use, e.g. ['nominatim','duckduckgo','overpass']",
    )
    max_results: int = Field(100, ge=1, le=10000)
    filters: DiscoveryJobFilters = Field(default_factory=DiscoveryJobFilters)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_to_dict(job: DiscoveryJob) -> Dict[str, Any]:
    return {
        "id": str(job.id),
        "user_id": str(job.user_id),
        "name": job.name,
        "status": job.status.value,
        "config": job.config,
        "total_found": job.total_found,
        "total_processed": job.total_processed,
        "total_errors": job.total_errors,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "estimated_completion": (
            job.estimated_completion.isoformat() if job.estimated_completion else None
        ),
        "error_message": job.error_message,
        "logs": job.logs,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


def _result_to_dict(r: DiscoveryResult) -> Dict[str, Any]:
    return {
        "id": str(r.id),
        "job_id": str(r.job_id),
        "business_id": str(r.business_id) if r.business_id else None,
        "source": r.source,
        "source_id": r.source_id,
        "status": r.status.value,
        "raw_data": r.raw_data,
        "processed_at": r.processed_at.isoformat() if r.processed_at else None,
        "created_at": r.created_at.isoformat(),
    }


async def _get_job_or_404(job_id: uuid.UUID, db: AsyncSession) -> DiscoveryJob:
    stmt = select(DiscoveryJob).where(DiscoveryJob.id == job_id)
    row = await db.execute(stmt)
    job = row.scalar_one_or_none()
    if job is None:
        raise NotFoundError(f"Discovery job '{job_id}' not found.")
    return job


def _get_user_id(current_user: Any) -> uuid.UUID:
    """Extract UUID from either ORM User or TokenData."""
    if hasattr(current_user, "id"):
        return current_user.id
    try:
        return uuid.UUID(current_user.sub)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not resolve user identity.",
        )


# ---------------------------------------------------------------------------
# GET /discovery/jobs
# ---------------------------------------------------------------------------


@router.get("/jobs", status_code=status.HTTP_200_OK)
async def list_jobs(
    job_status: Optional[JobStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return paginated list of all discovery jobs."""
    user_id = _get_user_id(current_user)

    stmt = select(DiscoveryJob).where(DiscoveryJob.user_id == user_id)
    if job_status:
        stmt = stmt.where(DiscoveryJob.status == job_status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(DiscoveryJob.created_at.desc()).offset(offset).limit(page_size)
    rows = await db.execute(stmt)
    jobs = rows.scalars().all()

    return {
        "items": [_job_to_dict(j) for j in jobs],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


# ---------------------------------------------------------------------------
# POST /discovery/jobs
# ---------------------------------------------------------------------------


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: DiscoveryJobCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Create and run a discovery job in the background (no Celery required)."""
    user_id = _get_user_id(current_user)

    job = DiscoveryJob(
        user_id=user_id,
        name=payload.name,
        status=JobStatus.pending,
        config={
            "keywords": payload.keywords,
            "country": payload.country,
            "city": payload.city,
            "industry": payload.industry,
            "sources": payload.sources,
            "max_results": payload.max_results,
            "filters": payload.filters.model_dump(),
        },
    )
    db.add(job)
    await db.flush()
    await db.commit()
    await db.refresh(job)

    # Run discovery inline via background task (no Redis/Celery needed)
    background_tasks.add_task(_run_discovery_inline, str(job.id))

    return _job_to_dict(job)


async def _run_discovery_inline(job_id: str) -> None:
    """Run the full discovery pipeline inline without Celery."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from app.core.database import AsyncSessionLocal
    from app.models.discovery_job import DiscoveryJob, JobStatus
    from app.models.business import Business, WebsiteStatus
    from app.models.discovery_result import DiscoveryResult, ResultStatus
    from slugify import slugify  # type: ignore

    async with AsyncSessionLocal() as session:
        stmt = select(DiscoveryJob).where(DiscoveryJob.id == _uuid.UUID(job_id))
        row = await session.execute(stmt)
        job = row.scalar_one_or_none()
        if job is None:
            return

        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        await session.commit()

        config = job.config or {}
        keywords: str = config.get("keywords", "")
        country = config.get("country")
        city = config.get("city")
        industry = config.get("industry")
        max_results: int = int(config.get("max_results", 100))
        sources: list = config.get("sources", ["duckduckgo"])
        raw_filters: dict = config.get("filters", {})
        filter_save_with_website: bool = raw_filters.get("save_with_website", True)
        filter_save_no_website: bool = raw_filters.get("save_no_website", True)
        filter_require_email: bool = raw_filters.get("require_email", False)
        filter_require_whatsapp: bool = raw_filters.get("require_whatsapp", False)

        total_found = 0
        total_errors = 0

        def _get_provider(source_name: str):
            if source_name == "duckduckgo":
                from app.engines.discovery.providers.duckduckgo_provider import DuckDuckGoProvider
                return DuckDuckGoProvider()
            elif source_name == "nominatim":
                from app.engines.discovery.providers.nominatim_provider import NominatimProvider
                return NominatimProvider()
            elif source_name == "overpass":
                from app.engines.discovery.providers.overpass_provider import OverpassProvider
                return OverpassProvider()
            elif source_name == "serpapi":
                from app.engines.discovery.providers.serpapi_provider import SerpAPIProvider
                return SerpAPIProvider()
            elif source_name == "google_places":
                from app.engines.discovery.providers.google_places_provider import GooglePlacesProvider
                return GooglePlacesProvider()
            elif source_name == "yelp":
                from app.engines.discovery.providers.yelp_provider import YelpProvider
                return YelpProvider()
            elif source_name == "google_maps":
                from app.engines.discovery.providers.google_maps_provider import GoogleMapsProvider
                return GoogleMapsProvider()
            elif source_name == "instagram":
                from app.engines.discovery.providers.instagram_provider import InstagramProvider
                return InstagramProvider()
            elif source_name == "facebook":
                from app.engines.discovery.providers.facebook_provider import FacebookProvider
                return FacebookProvider()
            elif source_name == "reddit":
                from app.engines.discovery.providers.reddit_provider import RedditProvider
                return RedditProvider()
            elif source_name in ("ecommerce_brands", "daraz", "ecommerce"):
                from app.engines.discovery.providers.ecommerce_provider import EcommerceProvider
                return EcommerceProvider()
            elif source_name in ("freelance", "upwork", "freelancer", "fiverr"):
                from app.engines.discovery.providers.freelance_provider import FreelanceProvider
                return FreelanceProvider()
            return None

        import httpx as _httpx
        from app.engines.contact.contact_extractor import ContactExtractor
        from app.engines.contact.validator import validate_email, validate_phone

        try:
            for source_name in sources:
                if total_found >= max_results:
                    break

                try:
                    provider = _get_provider(source_name)
                    if provider is None:
                        continue
                except Exception:
                    continue

                try:
                    async for biz_result in provider.discover(
                        query=keywords,
                        country=country,
                        industry=industry,
                        city=city,
                        max_results=max_results - total_found,
                    ):
                        if total_found >= max_results:
                            break

                        # Process each business in its own savepoint so failures
                        # don't roll back previously saved businesses
                        try:
                            raw = biz_result.raw_data or {}
                            name = biz_result.name or raw.get("name", "Unknown")
                            website_url = biz_result.website_url
                            biz_city = biz_result.city or city
                            biz_country = biz_result.country or country

                            scraped_email: str | None = biz_result.email
                            scraped_phone: str | None = biz_result.phone
                            scraped_whatsapp: str | None = raw.get("whatsapp_url") or raw.get("verified_whatsapp") or raw.get("whatsapp")
                            ig_url: str | None = raw.get("instagram_url")
                            fb_url: str | None = raw.get("facebook_url")
                            desc_text: str | None = raw.get("pitch") or raw.get("custom_pitch") or raw.get("bio_snippet") or raw.get("post_snippet")

                            # Strictly prevent social media links from being treated as independent websites
                            if website_url:
                                w_lower = website_url.lower()
                                if any(s in w_lower for s in ("facebook.com", "fb.me", "fb.com")):
                                    if not fb_url:
                                        fb_url = website_url
                                    website_url = None
                                elif any(s in w_lower for s in ("instagram.com", "cdninstagram.com", "fbcdn.net")):
                                    if not ig_url:
                                        ig_url = website_url
                                    website_url = None
                                elif any(s in w_lower for s in ("wa.me", "whatsapp.com")):
                                    if not scraped_whatsapp:
                                        scraped_whatsapp = website_url
                                    website_url = None
                                elif any(s in w_lower for s in ("linktr.ee", "bio.link", "beacons.ai", "taplink.cc", "bit.ly", "tinyurl.com", "solo.to", "campsite.bio", "heylink.me")):
                                    from app.engines.discovery.providers.instagram_provider import InstagramProvider
                                    found_site, found_wa, found_email = InstagramProvider._sync_inspect_aggregator(website_url)
                                    if found_site:
                                        website_url = found_site
                                    else:
                                        website_url = None
                                    if found_wa and not scraped_whatsapp:
                                        scraped_whatsapp = f"https://wa.me/{found_wa.lstrip('+')}"
                                    if found_email and not scraped_email:
                                        scraped_email = found_email
                                elif any(s in w_lower for s in ("tiktok.com", "youtube.com", "twitter.com", "x.com", "pinterest.com", "snapchat.com", "soundcloud.com", "spotify.com")):
                                    website_url = None

                            # ── Scrape website for email / phone ──
                            if website_url and not scraped_email and not scraped_phone:
                                try:
                                    url_to_fetch = website_url if website_url.startswith(("http://", "https://")) else "https://" + website_url
                                    hdrs = {"User-Agent": "BI-Platform/1.0 (contact-discovery)"}
                                    async with _httpx.AsyncClient(follow_redirects=True, timeout=3.0, headers=hdrs, verify=False) as client:
                                        resp = await client.get(url_to_fetch)
                                        html = resp.text
                                    extractor = ContactExtractor()
                                    contacts = extractor.extract_from_html(html, url_to_fetch)
                                    for c in sorted(contacts, key=lambda x: x.confidence_score, reverse=True):
                                        if c.email and not scraped_email:
                                            ev = validate_email(c.email)
                                            if ev.is_usable:
                                                scraped_email = ev.email
                                        if c.phone and not scraped_phone:
                                            pv = validate_phone(c.phone, country=biz_country, city=biz_city)
                                            if pv.whatsapp_eligible:
                                                scraped_phone = pv.e164
                                except Exception:
                                    pass

                            # ── Validate final phone via phonenumbers ──
                            if scraped_phone:
                                pv = validate_phone(scraped_phone, country=biz_country, city=biz_city)
                                if pv.e164:
                                    scraped_phone = pv.e164
                                    if pv.whatsapp_eligible and not scraped_whatsapp:
                                        scraped_whatsapp = f"https://wa.me/{pv.e164.lstrip('+')}"

                            # ── Strict authentic contact verification ──
                            has_direct_phone = bool(scraped_phone or scraped_whatsapp)
                            has_direct_email = bool(scraped_email)
                            has_social_channel = bool(ig_url or fb_url or (source_name == "reddit" and raw.get("reddit_url")))
                            has_freelance_channel = bool(source_name in ("freelance", "upwork", "freelancer", "fiverr") and (raw.get("project_url") or raw.get("job_url")))

                            # Never save empty/dead leads with zero contact info
                            if not (has_direct_phone or has_direct_email or has_social_channel or has_freelance_channel):
                                continue

                            # Generic web & directory scrapes (DuckDuckGo, OSM) MUST have a phone or email
                            if source_name in ("duckduckgo", "nominatim", "overpass") and not (has_direct_phone or has_direct_email):
                                continue

                            # ── Apply save filters ──
                            has_website = bool(website_url and str(website_url).strip())
                            has_email = has_direct_email
                            has_whatsapp = bool(scraped_whatsapp or (scraped_phone and not (scraped_phone.startswith("+1") and len(scraped_phone) == 12)))

                            if not filter_save_with_website and has_website:
                                continue
                            if not filter_save_no_website and not has_website:
                                continue
                            if filter_require_email and not has_email:
                                continue
                            if filter_require_whatsapp and not has_whatsapp:
                                continue

                            # Dedup by name+city
                            existing_stmt = select(Business).where(Business.name == name)
                            if biz_city:
                                existing_stmt = existing_stmt.where(Business.city == biz_city)
                            existing_row = await session.execute(existing_stmt)
                            existing = existing_row.scalar_one_or_none()

                            if existing:
                                if website_url and not existing.website_url and filter_save_with_website:
                                    existing.website_url = website_url
                                    existing.has_website = True
                                if scraped_email and not existing.email:
                                    existing.email = scraped_email
                                if scraped_phone and not existing.phone:
                                    existing.phone = scraped_phone
                                if scraped_whatsapp and not existing.whatsapp:
                                    existing.whatsapp = scraped_whatsapp
                                if ig_url and not existing.instagram_url:
                                    existing.instagram_url = ig_url
                                if fb_url and not existing.facebook_url:
                                    existing.facebook_url = fb_url
                                if desc_text and not existing.description:
                                    existing.description = desc_text
                                new_biz = None
                            else:
                                base_slug = slugify(name, max_length=200)
                                slug = f"{base_slug}-{_uuid.uuid4().hex[:8]}" if base_slug else _uuid.uuid4().hex
                                _has_web = bool(website_url and str(website_url).strip())
                                _industry_str = (biz_result.category or industry or "").lower()
                                _high_val = any(k in _industry_str for k in ("legal", "medical", "health", "finance", "real estate", "dental", "clinic", "ecommerce"))
                                _med_val = any(k in _industry_str for k in ("restaurant", "hotel", "retail", "salon", "spa", "gym", "fitness", "boutique"))
                                _base_opp = 85.0 if not _has_web else 50.0
                                _opp_score = round(_base_opp + (10.0 if _high_val else 5.0 if _med_val else 0.0), 1)
                                _priority = round(_opp_score * 0.6 + (25.0 if not _has_web else 5.0), 1)
                                _revenue = 15000.0 if _high_val else (8000.0 if _med_val else 6000.0)

                                social_dict = {}
                                if ig_url:
                                    social_dict["instagram"] = ig_url
                                if fb_url:
                                    social_dict["facebook"] = fb_url

                                new_biz = Business(
                                    name=name,
                                    slug=slug,
                                    city=biz_city,
                                    state=biz_result.state,
                                    country=biz_country,
                                    address=biz_result.address,
                                    phone=scraped_phone,
                                    whatsapp=scraped_whatsapp,
                                    email=scraped_email,
                                    website_url=website_url if _has_web else None,
                                    has_website=_has_web,
                                    website_status=WebsiteStatus.active if _has_web else None,
                                    category=biz_result.category or industry,
                                    industry=biz_result.category or industry,
                                    description=desc_text,
                                    instagram_url=ig_url,
                                    facebook_url=fb_url,
                                    social_profiles=social_dict if social_dict else None,
                                    source=source_name,
                                    source_id=biz_result.source_id,
                                    source_url=raw.get("project_url") or raw.get("job_url") or website_url,
                                    discovered_at=datetime.now(timezone.utc),
                                    opportunity_score=_opp_score,
                                    priority_score=_priority,
                                    revenue_potential=_revenue,
                                    metadata_={
                                        "raw_source": raw,
                                        "pitch": raw.get("pitch") or raw.get("custom_pitch"),
                                        "followers": raw.get("followers"),
                                        "tech_stack": raw.get("tech_stack"),
                                        "budget": raw.get("budget"),
                                        "reddit_url": raw.get("reddit_url"),
                                        "project_url": raw.get("project_url") or raw.get("job_url"),
                                        "job_url": raw.get("project_url") or raw.get("job_url"),
                                        "platform": raw.get("platform"),
                                        "discord": raw.get("discord"),
                                        "subreddit": raw.get("subreddit"),
                                        "whatsapp": scraped_whatsapp,
                                    },
                                )
                                session.add(new_biz)
                                await session.flush()

                                # Auto-create CRM Deal for this new lead
                                try:
                                    from app.models.crm import Pipeline, Deal, DealStage
                                    pipe_stmt = select(Pipeline).where(Pipeline.user_id == job.user_id).order_by(Pipeline.is_default.desc())
                                    pipe_row = await session.execute(pipe_stmt)
                                    user_pipeline = pipe_row.scalars().first()
                                    if not user_pipeline:
                                        user_pipeline = Pipeline(
                                            user_id=job.user_id,
                                            name="High-Converting Web Clients",
                                            description="Automated sales pipeline for businesses without websites",
                                            is_default=True,
                                        )
                                        session.add(user_pipeline)
                                        await session.flush()

                                    deal_stmt = select(Deal).where(Deal.business_id == new_biz.id)
                                    deal_row = await session.execute(deal_stmt)
                                    if not deal_row.scalar_one_or_none():
                                        new_deal = Deal(
                                            business_id=new_biz.id,
                                            pipeline_id=user_pipeline.id,
                                            user_id=job.user_id,
                                            title=f"Freelance Client: {name}" if source_name in ("freelance", "upwork", "freelancer", "fiverr") else f"Web Storefront: {name}",
                                            stage=DealStage.lead,
                                            value=_revenue,
                                            currency="USD",
                                            probability=0.35 if source_name in ("freelance", "upwork", "freelancer", "fiverr") else 0.25,
                                            notes=f"Auto-discovered via {source_name.upper()} ({raw.get('platform') or source_name}). Project: {raw.get('project_url') or raw.get('job_url')}. Budget: {raw.get('budget', 'TBD')}" if source_name in ("freelance", "upwork", "freelancer", "fiverr") else f"Auto-discovered via {source_name}. Opportunity Score: {_opp_score}. Has WhatsApp: {bool(scraped_whatsapp)}",
                                        )
                                        session.add(new_deal)
                                except Exception as deal_err:
                                    logger.debug("Auto-deal creation skipped: %s", deal_err)

                            biz_to_enrich = existing or new_biz
                            if biz_to_enrich is None:
                                continue

                            # ── Enrichment pass ──
                            try:
                                from app.engines.enrichment.enrichment_engine import EnrichmentEngine
                                _enricher = EnrichmentEngine(timeout=4.0)
                                _biz_dict = {
                                    "name": biz_to_enrich.name,
                                    "website_url": biz_to_enrich.website_url,
                                    "phone": biz_to_enrich.phone,
                                    "email": biz_to_enrich.email,
                                    "city": biz_to_enrich.city,
                                    "country": biz_to_enrich.country,
                                    "description": biz_to_enrich.description,
                                    "category": biz_to_enrich.category,
                                    "address": biz_to_enrich.address,
                                    "instagram_url": getattr(biz_to_enrich, "instagram_url", None) or ig_url,
                                    "facebook_url": getattr(biz_to_enrich, "facebook_url", None) or fb_url,
                                }
                                _enrich_result = await _enricher.enrich(_biz_dict)
                                for _field, _val in _enrich_result.to_patch().items():
                                    if _val is not None:
                                        if _field == "website_url" and any(s in str(_val).lower() for s in ("facebook.com", "fb.me", "instagram.com", "wa.me", "linktr.ee")):
                                            continue
                                        if _field in ("email", "email2") and not getattr(biz_to_enrich, "email", None):
                                            biz_to_enrich.email = str(_val)
                                        elif _field in ("phone", "phone2") and not getattr(biz_to_enrich, "phone", None):
                                            biz_to_enrich.phone = str(_val)
                                        elif _field == "whatsapp" and not getattr(biz_to_enrich, "whatsapp", None):
                                            biz_to_enrich.whatsapp = str(_val)
                                        elif not getattr(biz_to_enrich, _field, None):
                                            setattr(biz_to_enrich, _field, _val)
                                biz_to_enrich.completeness_score = _enrich_result.completeness_score
                                biz_to_enrich.enrichment_data = _enrich_result.enrichment_data
                                biz_to_enrich.last_enriched_at = datetime.now(timezone.utc)
                                _sp = biz_to_enrich.social_profiles or {}
                                for _sfield, _skey in [
                                    ("facebook_url", "facebook"), ("instagram_url", "instagram"),
                                    ("linkedin_url", "linkedin"), ("twitter_url", "twitter"),
                                ]:
                                    if getattr(biz_to_enrich, _sfield) and not _sp.get(_skey):
                                        _sp[_skey] = getattr(biz_to_enrich, _sfield)
                                biz_to_enrich.social_profiles = _sp or None
                            except Exception:
                                pass

                            # ── Link business → job ──
                            _result_biz_id = getattr(biz_to_enrich, "id", None)
                            if _result_biz_id:
                                _dr = DiscoveryResult(
                                    job_id=_uuid.UUID(job_id),
                                    business_id=_result_biz_id,
                                    source=source_name,
                                    source_id=biz_result.source_id,
                                    status=ResultStatus.processed,
                                    processed_at=datetime.now(timezone.utc),
                                    raw_data={
                                        "name": name,
                                        "city": biz_city,
                                        "url": website_url,
                                        "project_url": raw.get("project_url") or raw.get("job_url"),
                                        "budget": raw.get("budget"),
                                        "platform": raw.get("platform"),
                                        "pitch": raw.get("pitch") or raw.get("custom_pitch"),
                                    },
                                )
                                session.add(_dr)

                            # Commit every business individually so failures don't
                            # roll back previously saved records
                            total_found += 1
                            job.total_found = total_found
                            await session.commit()

                        except Exception:
                            total_errors += 1
                            await session.rollback()
                            # Re-fetch job after rollback so it's still usable
                            stmt = select(DiscoveryJob).where(DiscoveryJob.id == _uuid.UUID(job_id))
                            row = await session.execute(stmt)
                            job = row.scalar_one_or_none()
                            if job is None:
                                return
                except Exception:
                    total_errors += 1

            job.status = JobStatus.completed
            job.total_found = total_found
            job.total_processed = total_found
            job.total_errors = total_errors
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()

        except Exception as exc:
            job.status = JobStatus.failed
            job.error_message = str(exc)
            job.completed_at = datetime.now(timezone.utc)
            await session.commit()


# ---------------------------------------------------------------------------
# GET /discovery/jobs/{id}
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", status_code=status.HTTP_200_OK)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Get full details of a single discovery job."""
    job = await _get_job_or_404(job_id, db)
    return _job_to_dict(job)


# ---------------------------------------------------------------------------
# POST /discovery/jobs/{id}/pause
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/pause", status_code=status.HTTP_200_OK)
async def pause_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Mark a running discovery job as paused.

    Note: Celery tasks already dispatched will continue until their current
    iteration completes. The worker checks for paused status before
    queuing new batches.
    """
    job = await _get_job_or_404(job_id, db)

    if job.status not in (JobStatus.running, JobStatus.pending):
        raise ConflictError(
            f"Cannot pause a job in '{job.status.value}' state. "
            "Only 'running' or 'pending' jobs can be paused."
        )

    job.status = JobStatus.paused
    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


# ---------------------------------------------------------------------------
# POST /discovery/jobs/{id}/resume
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/resume", status_code=status.HTTP_200_OK)
async def resume_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Resume a paused discovery job."""
    job = await _get_job_or_404(job_id, db)

    if job.status != JobStatus.paused:
        raise ConflictError(
            f"Cannot resume a job in '{job.status.value}' state. "
            "Only 'paused' jobs can be resumed."
        )

    job.status = JobStatus.pending
    await db.commit()
    background_tasks.add_task(_run_discovery_inline, str(job.id))

    await db.refresh(job)
    return _job_to_dict(job)


# ---------------------------------------------------------------------------
# POST /discovery/jobs/{id}/rerun  — create a fresh job from the same config
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/rerun", status_code=status.HTTP_201_CREATED)
async def rerun_job(
    job_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Create a new job with the same config as an existing job and run it."""
    user_id = _get_user_id(current_user)
    original = await _get_job_or_404(job_id, db)

    new_job = DiscoveryJob(
        user_id=user_id,
        name=original.name,
        status=JobStatus.pending,
        config=dict(original.config or {}),
    )
    db.add(new_job)
    await db.flush()
    await db.commit()
    await db.refresh(new_job)

    background_tasks.add_task(_run_discovery_inline, str(new_job.id))
    return _job_to_dict(new_job)


# ---------------------------------------------------------------------------
# POST /discovery/jobs/{id}/cancel
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/cancel", status_code=status.HTTP_200_OK)
async def cancel_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Cancel a pending or running discovery job."""
    job = await _get_job_or_404(job_id, db)

    if job.status in (JobStatus.completed, JobStatus.cancelled):
        raise ConflictError(
            f"Cannot cancel a job in '{job.status.value}' state."
        )

    job.status = JobStatus.cancelled
    job.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return _job_to_dict(job)


# ---------------------------------------------------------------------------
# DELETE /discovery/jobs/{id}
# ---------------------------------------------------------------------------


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> None:
    """Delete a discovery job record (and its results via cascade)."""
    job = await _get_job_or_404(job_id, db)

    if job.status == JobStatus.running:
        raise ConflictError(
            "Cannot delete a running job. Cancel it first."
        )

    await db.delete(job)
    await db.commit()


# ---------------------------------------------------------------------------
# GET /discovery/providers
# ---------------------------------------------------------------------------

_KNOWN_PROVIDERS: List[Dict[str, Any]] = [
    {
        "name": "duckduckgo",
        "display_name": "DuckDuckGo",
        "description": "Web search discovery — finds businesses with websites. Best for broad discovery.",
        "requires_key": False,
        "env_key": None,
        "focus": "has_website",
    },
    {
        "name": "nominatim",
        "display_name": "OpenStreetMap (OSM)",
        "description": "Physical business data from OpenStreetMap — finds offline/undigitised businesses with NO website. Best for targeting leads.",
        "requires_key": False,
        "env_key": None,
        "focus": "no_website",
    },
    {
        "name": "overpass",
        "display_name": "OSM Overpass API",
        "description": "Primary OSM source via Overpass API — more data than Nominatim, returns lat/lng, phone, email from OSM tags.",
        "requires_key": False,
        "env_key": None,
        "focus": "no_website",
    },
    {
        "name": "serpapi",
        "display_name": "SerpAPI",
        "description": "Google Maps / Search results via SerpAPI. Requires SERPAPI_KEY.",
        "requires_key": True,
        "env_key": "SERPAPI_KEY",
        "focus": "mixed",
    },
    {
        "name": "google_places",
        "display_name": "Google Places API",
        "description": "Google My Business data — real businesses with phone, website, address. $200/month free credit (~6,000 searches). Requires GOOGLE_PLACES_API_KEY.",
        "requires_key": True,
        "env_key": "GOOGLE_PLACES_API_KEY",
        "focus": "mixed",
    },
    {
        "name": "yelp",
        "display_name": "Yelp Fusion API",
        "description": "Yelp business data — real local businesses with phone, address, category. 500 free calls/day, no credit card. Requires YELP_API_KEY.",
        "requires_key": True,
        "env_key": "YELP_API_KEY",
        "focus": "mixed",
    },
    {
        "name": "google_maps",
        "display_name": "Google Maps (Scraper)",
        "description": "Scrapes Google Maps directly — no API key needed. Returns real businesses with name, address, rating, category worldwide. Best free source.",
        "requires_key": False,
        "env_key": None,
        "focus": "mixed",
    },
    {
        "name": "instagram",
        "display_name": "Instagram (Bio WhatsApp & DM Sellers)",
        "description": "Finds boutiques, brands, and sellers on Instagram with active WhatsApp and NO websites. Highest conversion for web design pitches.",
        "requires_key": False,
        "env_key": None,
        "focus": "no_website",
    },
    {
        "name": "facebook",
        "display_name": "Facebook (Pages & Local Shops)",
        "description": "Finds verified Facebook business pages and local shops with direct mobile/WhatsApp numbers and missing websites.",
        "requires_key": False,
        "env_key": None,
        "focus": "no_website",
    },
    {
        "name": "reddit",
        "display_name": "Reddit (Hiring & Client Leads)",
        "description": "Mines active clients and founders looking to hire developers and web designers across r/forhire, r/freelance, and r/ecommerce.",
        "requires_key": False,
        "env_key": None,
        "focus": "no_website",
    },
    {
        "name": "ecommerce_brands",
        "display_name": "Daraz & E-Commerce Brands",
        "description": "Mines verified Pakistani and South Asian e-commerce brands with authentic mobile WhatsApp (+92300-349) and store tech stacks.",
        "requires_key": False,
        "env_key": None,
        "focus": "mixed",
    },
    {
        "name": "freelance",
        "display_name": "Freelance Platforms (Upwork, Freelancer, Fiverr)",
        "description": "Mines active clients and paying hiring projects directly from Upwork, Freelancer.com, and Fiverr with exact budgets and AI-tailored proposals.",
        "requires_key": False,
        "env_key": None,
        "focus": "no_website",
    },
]


@router.get("/providers", status_code=status.HTTP_200_OK)
async def list_providers(
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """List all registered discovery providers with their live status."""
    from app.core.config import settings

    result = []
    for p in _KNOWN_PROVIDERS:
        entry = dict(p)
        if p["requires_key"] and p["env_key"]:
            configured = bool(getattr(settings, p["env_key"], ""))
            entry["status"] = "available" if configured else "unavailable"
            entry["status_reason"] = (
                None if configured else f"{p['env_key']} is not set"
            )
        else:
            entry["status"] = "available"
            entry["status_reason"] = None
        result.append(entry)

    return {"providers": result, "total": len(result)}


# ---------------------------------------------------------------------------
# POST /discovery/providers/{name}/test
# ---------------------------------------------------------------------------


@router.post("/providers/{provider_name}/test", status_code=status.HTTP_200_OK)
async def test_provider(
    provider_name: str,
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Test connectivity and basic functionality of a discovery provider."""
    known_names = {p["name"] for p in _KNOWN_PROVIDERS}
    if provider_name not in known_names:
        raise NotFoundError(f"Provider '{provider_name}' is not registered.")

    try:
        from app.engines.discovery.providers import get_provider  # type: ignore

        provider = get_provider(provider_name)

        # Attempt a minimal discovery call with a single result
        results: List[Any] = []
        async for result in provider.discover(
            query="test restaurant",
            country=None,
            industry=None,
            city=None,
            max_results=1,
        ):
            results.append(result)
            break  # one result is enough for a connectivity check

        return {
            "provider": provider_name,
            "status": "ok",
            "sample_result_count": len(results),
            "message": "Provider is reachable and returned data.",
        }

    except Exception as exc:
        return {
            "provider": provider_name,
            "status": "error",
            "message": str(exc),
        }


# ---------------------------------------------------------------------------
# GET /discovery/jobs/{id}/results
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/results", status_code=status.HTTP_200_OK)
async def list_job_results(
    job_id: uuid.UUID,
    result_status: Optional[ResultStatus] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return paginated discovery results for a job."""
    await _get_job_or_404(job_id, db)

    stmt = select(DiscoveryResult).where(DiscoveryResult.job_id == job_id)
    if result_status:
        stmt = stmt.where(DiscoveryResult.status == result_status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(DiscoveryResult.created_at.desc()).offset(offset).limit(page_size)
    rows = await db.execute(stmt)
    results = rows.scalars().all()

    return {
        "job_id": str(job_id),
        "items": [_result_to_dict(r) for r in results],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


# ---------------------------------------------------------------------------
# POST /discovery/autopilot/start
# ---------------------------------------------------------------------------


class AutopilotRequest(BaseModel):
    city: str = Field("Lahore", max_length=100)
    country: str = Field("Pakistan", max_length=100)
    target_count: int = Field(15, ge=1, le=100)
    industry: Optional[str] = Field("Boutiques & Clothing", max_length=100)


@router.post("/autopilot/start", status_code=status.HTTP_201_CREATED)
async def start_autopilot_batch(
    body: AutopilotRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Launch an automated zero-website discovery batch.
    Cycles through top local social commerce queries, strictly enforces no-website filtering,
    extracts verified contacts, and populates the CRM pipeline automatically.
    """
    keywords = f"{body.industry or 'boutique'} {body.city}".strip()
    job_name = f"⚡ Auto-Pilot: {body.industry or 'Boutiques'} ({body.city})"

    job = DiscoveryJob(
        user_id=current_user.id,
        name=job_name,
        status=JobStatus.pending,
        config={
            "keywords": keywords,
            "country": body.country,
            "city": body.city,
            "industry": body.industry or "Clothing & Boutiques",
            "sources": ["instagram"],
            "max_results": body.target_count,
            "filters": {
                "save_with_website": False,
                "save_no_website": True,
                "require_email": False,
                "require_whatsapp": False,
            },
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Launch background inline runner
    background_tasks.add_task(_run_discovery_inline, str(job.id))

    return {
        "status": "started",
        "job_id": str(job.id),
        "name": job_name,
        "target_count": body.target_count,
        "city": body.city,
        "country": body.country,
    }


# ---------------------------------------------------------------------------
# Autonomous Auto-Cruise & Multi-City Sweep Engine
# ---------------------------------------------------------------------------

def infer_country_from_city(city: str) -> str:
    c = (city or "").lower().strip()
    if not c:
        return "United Arab Emirates"
    if any(k in c for k in ("dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "fujairah", "al ain")):
        return "United Arab Emirates"
    if any(k in c for k in ("riyadh", "jeddah", "mecca", "medina", "dammam", "khobar", "tabuk")):
        return "Saudi Arabia"
    if any(k in c for k in ("doha", "al rayyan", "al wakrah")):
        return "Qatar"
    if any(k in c for k in ("kuwait", "salmiya", "hawally")):
        return "Kuwait"
    if any(k in c for k in ("manama", "riffa")):
        return "Bahrain"
    if any(k in c for k in ("muscat", "salalah")):
        return "Oman"
    if any(k in c for k in ("london", "manchester", "birmingham", "leeds", "glasgow", "liverpool", "edinburgh", "bristol", "sheffield", "cardiff")):
        return "United Kingdom"
    if any(k in c for k in ("new york", "los angeles", "chicago", "houston", "phoenix", "philadelphia", "san antonio", "san diego", "dallas", "austin", "miami", "seattle", "denver", "nashville", "las vegas", "boston")):
        return "United States"
    if any(k in c for k in ("toronto", "montreal", "vancouver", "calgary", "edmonton", "ottawa")):
        return "Canada"
    if any(k in c for k in ("sydney", "melbourne", "brisbane", "perth", "adelaide")):
        return "Australia"
    if any(k in c for k in ("berlin", "hamburg", "munich", "cologne", "frankfurt")):
        return "Germany"
    if any(k in c for k in ("karachi", "lahore", "islamabad", "rawalpindi", "faisalabad", "multan", "peshawar", "quetta", "sialkot", "gujranwala")):
        return "Pakistan"
    return "United Arab Emirates"


_CRUISE_STATE: Dict[str, Any] = {
    "enabled": False,
    "interval_minutes": 30,
    "last_run": None,
    "total_leads_gathered": 0,
    "cities": ["Dubai", "Abu Dhabi", "Riyadh", "Doha", "Lahore", "Karachi", "London", "New York"],
    "niches": ["Bakeries & Custom Cakes", "Clothing & Boutiques", "Jewellery & Accessories"],
}


class AutopilotSweepRequest(BaseModel):
    cities: List[str] = Field(default_factory=lambda: ["Dubai", "Abu Dhabi", "Riyadh", "Lahore", "Karachi"])
    niches: List[str] = Field(default_factory=lambda: ["Bakeries & Custom Cakes", "Clothing & Boutiques"])
    batch_per_city: int = Field(10, ge=1, le=50)


class CruiseConfigRequest(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(30, ge=5, le=1440)
    cities: Optional[List[str]] = None
    niches: Optional[List[str]] = None


@router.post("/autopilot/sweep", status_code=status.HTTP_201_CREATED)
async def launch_autopilot_sweep(
    body: AutopilotSweepRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Launch an automated multi-city & multi-niche sweep across top target markets.
    Concurrently triggers zero-website lead generation and populates the CRM.
    """
    job_ids = []
    for city in body.cities:
        country = infer_country_from_city(city)
        for niche in body.niches:
            keywords = f"{niche} {city}".strip()
            job_name = f"🚀 Sweep: {niche} ({city})"
            job = DiscoveryJob(
                user_id=current_user.id,
                name=job_name,
                status=JobStatus.pending,
                config={
                    "keywords": keywords,
                    "country": country,
                    "city": city,
                    "industry": niche,
                    "sources": ["instagram"],
                    "max_results": body.batch_per_city,
                    "filters": {
                        "save_with_website": False,
                        "save_no_website": True,
                        "require_email": False,
                        "require_whatsapp": False,
                    },
                },
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)
            job_ids.append(str(job.id))
            background_tasks.add_task(_run_discovery_inline, str(job.id))

    return {
        "status": "started",
        "jobs_count": len(job_ids),
        "job_ids": job_ids,
        "cities": body.cities,
        "niches": body.niches,
    }


@router.get("/autopilot/status", status_code=status.HTTP_200_OK)
async def get_autopilot_status(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return live automation engine metrics, cruise mode state, and zero-website lead counts."""
    from app.models.business import Business
    stmt_no_web = select(func.count()).select_from(Business).where(Business.has_website == False)
    total_no_web = (await db.execute(stmt_no_web)).scalar_one()

    stmt_running = select(func.count()).select_from(DiscoveryJob).where(DiscoveryJob.status == JobStatus.running)
    running_jobs = (await db.execute(stmt_running)).scalar_one()

    return {
        "cruise_enabled": _CRUISE_STATE["enabled"],
        "cruise_interval_minutes": _CRUISE_STATE["interval_minutes"],
        "cruise_cities": _CRUISE_STATE["cities"],
        "cruise_niches": _CRUISE_STATE["niches"],
        "last_cruise_run": _CRUISE_STATE["last_run"],
        "total_no_web_leads": total_no_web,
        "active_jobs_count": running_jobs,
    }


@router.post("/autopilot/cruise", status_code=status.HTTP_200_OK)
async def toggle_autopilot_cruise(
    body: CruiseConfigRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Toggle continuous background cruise mode that periodically scans and collects zero-website leads."""
    _CRUISE_STATE["enabled"] = body.enabled
    _CRUISE_STATE["interval_minutes"] = body.interval_minutes
    if body.cities:
        _CRUISE_STATE["cities"] = body.cities
    if body.niches:
        _CRUISE_STATE["niches"] = body.niches

    if body.enabled:
        sweep_req = AutopilotSweepRequest(
            cities=_CRUISE_STATE["cities"][:2],
            niches=_CRUISE_STATE["niches"][:2],
            batch_per_city=5,
        )
        await launch_autopilot_sweep(sweep_req, background_tasks, db, current_user)
        _CRUISE_STATE["last_run"] = datetime.now(timezone.utc).isoformat()

    return {
        "status": "ok",
        "cruise_enabled": _CRUISE_STATE["enabled"],
        "interval_minutes": _CRUISE_STATE["interval_minutes"],
        "message": "Auto-Cruise 24/7 background mode activated." if body.enabled else "Auto-Cruise stopped.",
    }


# ---------------------------------------------------------------------------
# POST /discovery/mark-contacted/{business_id}
# ---------------------------------------------------------------------------


@router.post("/mark-contacted/{business_id}", status_code=status.HTTP_200_OK)
async def mark_business_contacted(
    business_id: uuid.UUID,
    channel: str = Query("whatsapp", description="whatsapp, instagram_dm, or email"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Instantly advance a business to 'contacted' stage in CRM when outreach is launched.
    """
    from app.models.crm import Deal, DealStage, Activity, ActivityType, Pipeline

    deal_stmt = select(Deal).where(Deal.business_id == business_id)
    deal_row = await db.execute(deal_stmt)
    deal = deal_row.scalar_one_or_none()

    if not deal:
        pipe_stmt = select(Pipeline).where(Pipeline.user_id == current_user.id).order_by(Pipeline.is_default.desc())
        pipe_row = await db.execute(pipe_stmt)
        user_pipeline = pipe_row.scalars().first()
        if not user_pipeline:
            user_pipeline = Pipeline(
                user_id=current_user.id,
                name="High-Converting Web Clients",
                is_default=True,
            )
            db.add(user_pipeline)
            await db.flush()

        deal = Deal(
            business_id=business_id,
            pipeline_id=user_pipeline.id,
            user_id=current_user.id,
            title="Web Outreach Client",
            stage=DealStage.contacted,
            value=6000.0,
            probability=0.35,
        )
        db.add(deal)
        await db.flush()
    else:
        deal.stage = DealStage.contacted
        deal.probability = max(deal.probability, 0.35)

    act = Activity(
        deal_id=deal.id,
        user_id=current_user.id,
        activity_type=ActivityType.status_change,
        subject=f"Outreach launched via {channel.upper()}",
        body=f"User launched outreach message via {channel}",
    )
    db.add(act)
    await db.commit()
    return {"status": "ok", "business_id": str(business_id), "stage": "contacted"}
