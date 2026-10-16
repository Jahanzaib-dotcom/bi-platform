"""
Audit endpoints.

Routes
------
GET    /audits               – list all audits, filterable
GET    /audits/stats         – aggregate audit statistics  (before /{id})
POST   /audits/bulk          – bulk audit trigger           (before /{id})
GET    /audits/{id}          – full audit report
POST   /audits               – trigger audit for a URL
DELETE /audits/{id}          – delete an audit record
GET    /audits/{id}/screenshots – screenshots for an audit
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.core.security import oauth2_scheme, verify_token
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business
from app.models.screenshot import Screenshot
from app.models.user import User

router = APIRouter(prefix="/audits", tags=["audits"])


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


class AuditCreateRequest(BaseModel):
    """Trigger a fresh audit by providing a URL (business_id optional)."""

    url: str = Field(..., min_length=4, description="Website URL to audit")
    business_id: Optional[uuid.UUID] = Field(
        None, description="Associate with an existing business"
    )
    capture_screenshots: bool = True
    run_ai_analysis: bool = True


class BulkAuditRequest(BaseModel):
    business_ids: List[uuid.UUID] = Field(..., min_length=1, max_length=100)
    capture_screenshots: bool = True
    run_ai_analysis: bool = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
        "seo_issues": a.seo_issues,
        "accessibility_issues": a.accessibility_issues,
        "performance_metrics": a.performance_metrics,
        "recommendations": a.recommendations,
        "ai_analysis": a.ai_analysis,
        "tech_stack": a.tech_stack,
        "broken_links": a.broken_links,
        "error_message": a.error_message,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "completed_at": a.completed_at.isoformat() if a.completed_at else None,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
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


async def _get_audit_or_404(audit_id: uuid.UUID, db: AsyncSession) -> AuditReport:
    stmt = select(AuditReport).where(AuditReport.id == audit_id)
    row = await db.execute(stmt)
    audit = row.scalar_one_or_none()
    if audit is None:
        raise NotFoundError(f"Audit '{audit_id}' not found.")
    return audit


# ---------------------------------------------------------------------------
# GET /audits – list all audits
# ---------------------------------------------------------------------------


@router.get("", status_code=status.HTTP_200_OK)
async def list_audits(
    audit_status: Optional[AuditStatus] = Query(None, alias="status"),
    business_id: Optional[uuid.UUID] = Query(None),
    min_score: Optional[float] = Query(None, ge=0, le=100),
    max_score: Optional[float] = Query(None, ge=0, le=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return a paginated, filterable list of all audit reports."""
    stmt = select(AuditReport)

    if audit_status:
        stmt = stmt.where(AuditReport.status == audit_status)
    if business_id:
        stmt = stmt.where(AuditReport.business_id == business_id)
    if min_score is not None:
        stmt = stmt.where(AuditReport.overall_score >= min_score)
    if max_score is not None:
        stmt = stmt.where(AuditReport.overall_score <= max_score)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(AuditReport.created_at.desc()).offset(offset).limit(page_size)
    rows = await db.execute(stmt)
    audits = rows.scalars().all()

    return {
        "items": [_audit_to_dict(a) for a in audits],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if total else 0,
    }


# ---------------------------------------------------------------------------
# GET /audits/stats  (MUST come before /{id})
# ---------------------------------------------------------------------------


@router.get("/stats", status_code=status.HTTP_200_OK)
async def audit_stats(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return aggregate statistics across all audit reports."""
    # Total counts by status
    status_counts: Dict[str, int] = {s.value: 0 for s in AuditStatus}
    count_rows = await db.execute(
        select(AuditReport.status, func.count(AuditReport.id).label("cnt"))
        .group_by(AuditReport.status)
    )
    for row in count_rows:
        status_counts[row.status.value] = row.cnt

    total = sum(status_counts.values())

    # Average scores across completed audits
    score_cols = [
        AuditReport.overall_score,
        AuditReport.seo_score,
        AuditReport.mobile_score,
        AuditReport.speed_score,
        AuditReport.accessibility_score,
        AuditReport.security_score,
        AuditReport.content_score,
        AuditReport.conversion_score,
    ]
    avg_row = await db.execute(
        select(*[func.avg(col).label(col.key) for col in score_cols]).where(
            AuditReport.status == AuditStatus.completed
        )
    )
    avg_data = avg_row.mappings().one_or_none() or {}

    avg_scores = {
        key: round(float(val), 1) if val is not None else None
        for key, val in avg_data.items()
    }

    return {
        "total": total,
        "by_status": status_counts,
        "average_scores": avg_scores,
    }


# ---------------------------------------------------------------------------
# POST /audits/bulk  (MUST come before /{id})
# ---------------------------------------------------------------------------


@router.post("/bulk", status_code=status.HTTP_202_ACCEPTED)
async def bulk_audit(
    payload: BulkAuditRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Queue audit tasks for multiple businesses using BackgroundTasks."""
    queued: list[str] = []
    skipped: list[str] = []

    for bid in payload.business_ids:
        biz = await db.get(Business, bid)
        if not biz:
            skipped.append(str(bid))
            continue

        url = biz.website_url
        if not url:
            skipped.append(str(bid))
            continue

        # Create an AuditReport record so _run_audit_inline has a valid audit_id
        audit = AuditReport(
            business_id=biz.id,
            website_url=url,
            status=AuditStatus.pending,
        )
        db.add(audit)
        await db.flush()

        background_tasks.add_task(
            _run_audit_inline,
            str(audit.id),
            str(biz.id),
            url,
        )
        queued.append(str(biz.id))

    await db.commit()
    return {
        "queued": queued,
        "skipped": skipped,
        "count": len(queued),
        "status": "queued",
    }


# ---------------------------------------------------------------------------
# GET /audits/{id}
# ---------------------------------------------------------------------------


@router.get("/{audit_id}", status_code=status.HTTP_200_OK)
async def get_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return the full audit report for a single audit."""
    audit = await _get_audit_or_404(audit_id, db)
    return _audit_to_dict(audit)


# ---------------------------------------------------------------------------
# POST /audits
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_audit(
    payload: AuditCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Trigger an audit for a given URL.

    Looks up or auto-creates a business record for the URL, then runs
    the audit pipeline inline (no Celery/Redis required).
    """
    from datetime import datetime, timezone
    from urllib.parse import urlparse
    import uuid as _uuid
    from app.models.business import WebsiteStatus

    # Normalize URL protocol
    normalized_url = payload.url
    if normalized_url and not normalized_url.startswith(("http://", "https://")):
        normalized_url = "https://" + normalized_url

    business_id: Optional[uuid.UUID] = payload.business_id

    # Try to find existing business by URL
    if business_id is None:
        stmt = select(Business).where(Business.website_url == normalized_url)
        row = await db.execute(stmt)
        biz = row.scalar_one_or_none()
        if biz:
            business_id = biz.id

    # Auto-create business from URL if still not found
    if business_id is None:
        parsed = urlparse(payload.url)
        domain = parsed.netloc or parsed.path
        name = domain.replace("www.", "").split(".")[0].title() or domain
        from slugify import slugify  # type: ignore
        slug = f"{slugify(name, max_length=200)}-{_uuid.uuid4().hex[:8]}"
        new_biz = Business(
            name=name,
            slug=slug,
            website_url=normalized_url,
            has_website=True,
            website_status=WebsiteStatus.active,
            source="manual",
            discovered_at=datetime.now(timezone.utc),
        )
        db.add(new_biz)
        await db.flush()
        await db.commit()
        await db.refresh(new_biz)
        business_id = new_biz.id

    # Create audit record in pending state
    audit = AuditReport(
        business_id=business_id,
        website_url=normalized_url,
        status=AuditStatus.pending,
    )
    db.add(audit)
    await db.flush()
    await db.commit()
    await db.refresh(audit)

    # Run audit inline via background task (no Celery needed)
    background_tasks.add_task(
        _run_audit_inline,
        str(audit.id),
        str(business_id),
        normalized_url,
    )

    return _audit_to_dict(audit)


async def _run_audit_inline(audit_id: str, business_id: str, url: str) -> None:
    """Comprehensive website audit: SEO, mobile, speed, UX, security, accessibility, content."""
    import uuid as _uuid
    import time
    import re
    from datetime import datetime, timezone
    from urllib.parse import urlparse, urljoin
    import httpx
    from bs4 import BeautifulSoup
    from app.core.database import AsyncSessionLocal
    from app.models.audit import AuditReport, AuditStatus

    async with AsyncSessionLocal() as session:
        stmt = select(AuditReport).where(AuditReport.id == _uuid.UUID(audit_id))
        row = await session.execute(stmt)
        audit = row.scalar_one_or_none()
        if audit is None:
            return

        audit.status = AuditStatus.running
        audit.started_at = datetime.now(timezone.utc)
        await session.commit()

        try:
            # Ensure URL has a protocol
            if url and not url.startswith(("http://", "https://")):
                url = "https://" + url

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }

            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=25.0, headers=headers, verify=False) as client:
                    resp = await client.get(url)
                    ttfb_ms = int((time.monotonic() - t0) * 1000)
                    html = resp.text
                    status_code = resp.status_code
                    final_url = str(resp.url)
                    resp_headers = dict(resp.headers)
            except Exception as e:
                audit.status = AuditStatus.failed
                audit.error_message = f"Failed to fetch {url}: {e}"
                audit.completed_at = datetime.now(timezone.utc)
                await session.commit()
                return

            soup = BeautifulSoup(html, "html.parser")
            html_lower = html.lower()
            page_size_kb = len(html.encode("utf-8")) / 1024
            seo_issues: List[Dict[str, Any]] = []
            accessibility_issues: List[Dict[str, Any]] = []
            recommendations: List[str] = []
            tech_stack: List[str] = []

            # ── SEO Analysis ──────────────────────────────────────────────────
            title_tag = soup.find("title")
            title_text = title_tag.get_text(strip=True) if title_tag else ""
            has_title = bool(title_text)
            title_len = len(title_text)

            meta_desc_tag = soup.find("meta", attrs={"name": "description"})
            meta_desc = (meta_desc_tag.get("content", "") or "") if meta_desc_tag else ""
            has_meta_desc = bool(meta_desc.strip())
            meta_desc_len = len(meta_desc)

            meta_keywords = soup.find("meta", attrs={"name": "keywords"})
            has_keywords = bool(meta_keywords)

            h1_tags = soup.find_all("h1")
            h2_tags = soup.find_all("h2")
            h3_tags = soup.find_all("h3")
            has_single_h1 = len(h1_tags) == 1
            has_h1 = len(h1_tags) >= 1

            canonical = soup.find("link", attrs={"rel": "canonical"})
            has_canonical = bool(canonical)

            og_title = soup.find("meta", attrs={"property": "og:title"})
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            og_image = soup.find("meta", attrs={"property": "og:image"})
            has_og = bool(og_title and og_desc)
            has_og_image = bool(og_image)

            twitter_card = soup.find("meta", attrs={"name": "twitter:card"})
            has_twitter = bool(twitter_card)

            structured_data = bool(soup.find("script", attrs={"type": "application/ld+json"}))

            robots_meta = soup.find("meta", attrs={"name": "robots"})
            noindex = bool(robots_meta and "noindex" in (robots_meta.get("content", "") or "").lower())

            img_tags = soup.find_all("img")
            imgs_with_alt = [img for img in img_tags if img.get("alt", "").strip()]
            imgs_missing_alt = len(img_tags) - len(imgs_with_alt)
            alt_ratio = len(imgs_with_alt) / len(img_tags) if img_tags else 1.0

            all_links = soup.find_all("a", href=True)
            internal_links = [a for a in all_links if not a["href"].startswith("http") or urlparse(a["href"]).netloc == urlparse(url).netloc]
            external_links = [a for a in all_links if a["href"].startswith("http") and urlparse(a["href"]).netloc != urlparse(url).netloc]

            # Word count estimate
            body = soup.find("body")
            text_content = body.get_text(separator=" ", strip=True) if body else ""
            word_count = len(text_content.split())

            seo_score_pts = 0
            if has_title: seo_score_pts += 15
            if has_title and 30 <= title_len <= 60: seo_score_pts += 5
            if has_meta_desc: seo_score_pts += 15
            if has_meta_desc and 120 <= meta_desc_len <= 160: seo_score_pts += 5
            if has_single_h1: seo_score_pts += 10
            if has_canonical: seo_score_pts += 8
            if has_og: seo_score_pts += 8
            if has_og_image: seo_score_pts += 4
            if has_twitter: seo_score_pts += 4
            if structured_data: seo_score_pts += 8
            if alt_ratio >= 0.9: seo_score_pts += 8
            elif alt_ratio >= 0.5: seo_score_pts += 4
            if word_count >= 300: seo_score_pts += 5
            if not noindex: seo_score_pts += 5
            seo_score = min(100, seo_score_pts)

            if not has_title:
                seo_issues.append({"title": "Missing <title> tag", "category": "seo", "severity": "critical", "description": "Every page must have a unique, descriptive title tag for SEO."})
                recommendations.append("Add a unique <title> tag (30-60 characters) to every page")
            elif title_len > 60:
                seo_issues.append({"title": "Title tag too long", "category": "seo", "severity": "warning", "description": f"Title is {title_len} chars. Keep it under 60 to avoid truncation in search results."})
                recommendations.append(f"Shorten your page title from {title_len} to under 60 characters")
            elif title_len < 30:
                seo_issues.append({"title": "Title tag too short", "category": "seo", "severity": "warning", "description": f"Title is only {title_len} chars. Aim for 30-60 for better click-through rates."})

            if not has_meta_desc:
                seo_issues.append({"title": "Missing meta description", "category": "seo", "severity": "critical", "description": "Meta descriptions appear in search results and directly impact click-through rates."})
                recommendations.append("Add a meta description (120-160 characters) summarizing the page content")
            elif meta_desc_len > 160:
                seo_issues.append({"title": "Meta description too long", "category": "seo", "severity": "warning", "description": f"Meta description is {meta_desc_len} chars. Keep under 160 to avoid truncation."})

            if len(h1_tags) == 0:
                seo_issues.append({"title": "No H1 heading found", "category": "seo", "severity": "critical", "description": "H1 is the most important heading for both SEO and accessibility."})
                recommendations.append("Add exactly one H1 heading that describes the main topic of the page")
            elif len(h1_tags) > 1:
                seo_issues.append({"title": f"Multiple H1 tags ({len(h1_tags)})", "category": "seo", "severity": "warning", "description": "Multiple H1s confuse search engines about the page's main topic."})
                recommendations.append(f"Reduce to a single H1 tag (currently {len(h1_tags)})")

            if not has_canonical:
                seo_issues.append({"title": "No canonical URL", "category": "seo", "severity": "warning", "description": "Canonical URLs prevent duplicate content issues."})
                recommendations.append("Add a canonical <link rel='canonical'> tag to prevent duplicate content issues")

            if not has_og:
                seo_issues.append({"title": "Missing Open Graph tags", "category": "seo", "severity": "info", "description": "Open Graph tags control how pages appear when shared on social media."})
                recommendations.append("Add Open Graph meta tags (og:title, og:description, og:image) for better social sharing")

            if not structured_data:
                recommendations.append("Add JSON-LD structured data (Schema.org) to help search engines understand your content")

            if imgs_missing_alt > 0:
                seo_issues.append({"title": f"{imgs_missing_alt} image(s) missing alt text", "category": "seo", "severity": "warning", "description": "Alt text helps search engines index images and is required for accessibility."})
                recommendations.append(f"Add descriptive alt text to {imgs_missing_alt} image(s)")

            if word_count < 300:
                seo_issues.append({"title": f"Thin content ({word_count} words)", "category": "seo", "severity": "warning", "description": "Pages with under 300 words are considered thin content by search engines."})
                recommendations.append(f"Expand page content — currently only {word_count} words, aim for at least 300")

            if noindex:
                seo_issues.append({"title": "Page set to noindex", "category": "seo", "severity": "critical", "description": "This page is blocked from appearing in search results."})

            # ── Mobile / Responsive ───────────────────────────────────────────
            viewport_meta = soup.find("meta", attrs={"name": "viewport"})
            has_viewport = bool(viewport_meta)
            viewport_content = (viewport_meta.get("content", "") or "") if viewport_meta else ""
            has_width_device = "width=device-width" in viewport_content

            # Check for responsive CSS indicators
            has_media_queries = "@media" in html
            has_responsive_framework = any(x in html_lower for x in ["bootstrap", "tailwind", "foundation", "bulma", "materialize"])
            has_fixed_width = bool(re.search(r'width\s*:\s*\d{3,4}px', html))

            mobile_score_pts = 0
            if has_viewport: mobile_score_pts += 30
            if has_width_device: mobile_score_pts += 20
            if has_media_queries: mobile_score_pts += 25
            if has_responsive_framework: mobile_score_pts += 15
            if not has_fixed_width: mobile_score_pts += 10
            mobile_score = min(100, mobile_score_pts)

            if not has_viewport:
                accessibility_issues.append({"title": "Missing viewport meta tag", "category": "mobile", "severity": "critical", "description": "Without viewport meta, mobile browsers render the page at desktop width."})
                recommendations.append("Add <meta name='viewport' content='width=device-width, initial-scale=1'> to the <head>")
            elif not has_width_device:
                accessibility_issues.append({"title": "Viewport not set to device-width", "category": "mobile", "severity": "warning", "description": "Set viewport to width=device-width for proper mobile scaling."})

            if not has_media_queries:
                recommendations.append("Add CSS media queries to create a responsive layout for mobile devices")

            # ── Performance / Speed ───────────────────────────────────────────
            # Render-blocking resources
            render_blocking_css = len(soup.find_all("link", attrs={"rel": "stylesheet"}))
            render_blocking_js = len([s for s in soup.find_all("script", src=True) if not s.get("async") and not s.get("defer")])
            inline_styles = len(soup.find_all("style"))

            # Image optimization hints
            lazy_imgs = len([img for img in img_tags if img.get("loading") == "lazy"])
            total_imgs = len(img_tags)
            unoptimized_imgs = total_imgs - lazy_imgs

            # Minification check (rough)
            avg_line_len = len(html) / max(html.count("\n"), 1)
            likely_minified = avg_line_len > 500

            speed_score_pts = 0
            if ttfb_ms < 200: speed_score_pts += 35
            elif ttfb_ms < 500: speed_score_pts += 28
            elif ttfb_ms < 1000: speed_score_pts += 18
            elif ttfb_ms < 2000: speed_score_pts += 10
            else: speed_score_pts += 3

            if page_size_kb < 100: speed_score_pts += 20
            elif page_size_kb < 300: speed_score_pts += 15
            elif page_size_kb < 500: speed_score_pts += 8
            else: speed_score_pts += 3

            if render_blocking_js == 0: speed_score_pts += 15
            elif render_blocking_js <= 3: speed_score_pts += 8
            else: speed_score_pts += 3

            if likely_minified: speed_score_pts += 10
            if unoptimized_imgs == 0 or total_imgs == 0: speed_score_pts += 10
            elif unoptimized_imgs <= 3: speed_score_pts += 5

            speed_score = min(100, speed_score_pts)

            if ttfb_ms > 2000:
                seo_issues.append({"title": f"Slow server response ({ttfb_ms}ms)", "category": "speed", "severity": "critical", "description": "Server response over 2s hurts both user experience and SEO rankings."})
                recommendations.append(f"Optimize server response time — currently {ttfb_ms}ms, target under 200ms. Consider caching, CDN, or server upgrades.")
            elif ttfb_ms > 1000:
                seo_issues.append({"title": f"Slow server response ({ttfb_ms}ms)", "category": "speed", "severity": "warning", "description": "Server response over 1s impacts user experience."})
                recommendations.append(f"Reduce server response time from {ttfb_ms}ms to under 500ms")

            if render_blocking_js > 3:
                recommendations.append(f"Add async/defer attributes to {render_blocking_js} render-blocking JavaScript files")
            if page_size_kb > 300:
                recommendations.append(f"Reduce HTML page size from {page_size_kb:.0f}KB — consider server-side rendering or removing unused markup")
            if unoptimized_imgs > 3:
                recommendations.append(f"Add loading='lazy' to {unoptimized_imgs} images to improve initial page load")

            # ── UI Design ─────────────────────────────────────────────────────
            has_favicon = bool(
                soup.find("link", attrs={"rel": lambda r: r and "icon" in r.lower()}) or
                soup.find("link", attrs={"rel": "shortcut icon"})
            )
            has_css = bool(soup.find("link", attrs={"rel": "stylesheet"})) or bool(soup.find("style"))
            has_custom_fonts = any(x in html_lower for x in ["fonts.googleapis.com", "fonts.gstatic.com", "typekit", "fontawesome", "font-awesome"])
            has_animations = any(x in html_lower for x in ["animate.css", "aos", "gsap", "framer-motion", "transition:", "animation:"])
            content_sections = len(soup.find_all(["section", "article", "main", "aside"]))
            has_cta = bool(re.search(r'contact|get.started|sign.?up|book|call.?us|free.?trial|get.?quote|learn.?more', html_lower))
            has_hero = bool(soup.find(class_=re.compile(r'hero|banner|jumbotron|cover', re.I))) or bool(soup.find(id=re.compile(r'hero|banner', re.I)))

            ui_score_pts = 0
            if status_code == 200: ui_score_pts += 15
            if has_css: ui_score_pts += 15
            if has_favicon: ui_score_pts += 10
            if has_custom_fonts: ui_score_pts += 8
            if has_responsive_framework: ui_score_pts += 10
            if has_animations: ui_score_pts += 7
            if content_sections >= 3: ui_score_pts += 10
            if has_cta: ui_score_pts += 10
            if has_hero: ui_score_pts += 10
            if has_og_image: ui_score_pts += 5
            ui_score = min(100, ui_score_pts)

            if not has_favicon:
                recommendations.append("Add a favicon to strengthen brand recognition in browser tabs and bookmarks")
            if not has_cta:
                recommendations.append("Add clear call-to-action buttons (e.g. 'Contact Us', 'Get a Quote', 'Book Now')")
            if content_sections < 2:
                recommendations.append("Structure content into distinct sections (hero, features, about, contact) for better visual hierarchy")

            # ── UX Analysis ───────────────────────────────────────────────────
            has_nav = bool(soup.find("nav")) or bool(soup.find(role="navigation"))
            has_footer = bool(soup.find("footer"))
            has_search = bool(soup.find("input", attrs={"type": "search"})) or bool(re.search(r'search', html_lower))
            has_contact_form = bool(soup.find("form")) and bool(re.search(r'contact|email|message|phone', html_lower))
            has_phone = bool(re.search(r'\+?[\d\s\-\(\)]{10,}', text_content))
            has_email = bool(re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html))
            has_address = bool(re.search(r'\d+\s+\w+\s+(street|st|avenue|ave|road|rd|blvd|lane|drive|dr|way)\b', html_lower))
            has_social = any(x in html_lower for x in ["facebook.com", "twitter.com", "instagram.com", "linkedin.com", "youtube.com", "tiktok.com"])
            has_map = any(x in html_lower for x in ["google.com/maps", "maps.googleapis", "openstreetmap", "mapbox"])
            has_live_chat = any(x in html_lower for x in ["intercom", "zendesk", "tawk.to", "crisp", "freshchat", "drift", "livechat"])
            has_reviews = any(x in html_lower for x in ["review", "testimonial", "rating", "stars", "trustpilot", "google review"])
            has_ssl_redirect = final_url.startswith("https://")

            ux_score_pts = 0
            if has_nav: ux_score_pts += 15
            if has_footer: ux_score_pts += 10
            if has_contact_form: ux_score_pts += 12
            if has_phone: ux_score_pts += 8
            if has_email: ux_score_pts += 8
            if has_social: ux_score_pts += 7
            if has_reviews: ux_score_pts += 10
            if has_cta: ux_score_pts += 10
            if has_search: ux_score_pts += 5
            if has_map: ux_score_pts += 5
            if has_live_chat: ux_score_pts += 5
            if has_address: ux_score_pts += 5
            ux_score = min(100, ux_score_pts)

            if not has_nav:
                accessibility_issues.append({"title": "No navigation menu found", "category": "ux", "severity": "warning", "description": "Clear navigation is essential for usability."})
                recommendations.append("Add a navigation menu so visitors can easily find key pages")
            if not has_footer:
                recommendations.append("Add a footer with contact information, links, and legal pages")
            if not has_contact_form:
                recommendations.append("Add a contact form — it significantly increases lead generation")
            if not has_phone:
                recommendations.append("Display a phone number prominently — it builds trust and drives calls")
            if not has_reviews:
                recommendations.append("Add customer reviews or testimonials — social proof increases conversion by up to 15%")
            if not has_social:
                recommendations.append("Add social media links to build brand presence and trust signals")
            if not has_map and has_address:
                recommendations.append("Embed a Google Map to help customers find your location easily")

            # ── Security Analysis ─────────────────────────────────────────────
            is_https = url.startswith("https://") or final_url.startswith("https://")
            hsts = "strict-transport-security" in {k.lower(): v for k, v in resp_headers.items()}
            csp = "content-security-policy" in {k.lower(): v for k, v in resp_headers.items()}
            x_frame = "x-frame-options" in {k.lower(): v for k, v in resp_headers.items()}
            x_content_type = "x-content-type-options" in {k.lower(): v for k, v in resp_headers.items()}
            referrer_policy = "referrer-policy" in {k.lower(): v for k, v in resp_headers.items()}
            server_header = resp_headers.get("server", "")
            exposes_server = bool(server_header and any(x in server_header.lower() for x in ["apache/", "nginx/", "php/", "iis/"]))

            security_pts = 0
            if is_https: security_pts += 35
            if hsts: security_pts += 15
            if csp: security_pts += 15
            if x_frame: security_pts += 10
            if x_content_type: security_pts += 10
            if referrer_policy: security_pts += 8
            if not exposes_server: security_pts += 7
            security_score = min(100, security_pts)

            if not is_https:
                seo_issues.append({"title": "Site not using HTTPS", "category": "security", "severity": "critical", "description": "HTTP sites are flagged as 'Not Secure' by browsers. Google uses HTTPS as a ranking signal."})
                recommendations.append("Migrate to HTTPS immediately — get a free SSL certificate from Let's Encrypt")
            if not hsts:
                recommendations.append("Add HSTS header (Strict-Transport-Security) to enforce HTTPS connections")
            if not csp:
                recommendations.append("Implement a Content Security Policy (CSP) header to prevent XSS attacks")
            if not x_frame:
                recommendations.append("Add X-Frame-Options header to prevent clickjacking attacks")
            if exposes_server:
                recommendations.append(f"Remove/hide server version from response headers (currently exposing: {server_header})")

            # ── Accessibility ─────────────────────────────────────────────────
            has_lang = bool(soup.find("html", lang=True))
            skip_link = bool(re.search(r'skip.*content|skip.*nav', html_lower))
            has_aria = bool(re.search(r'aria-', html))
            has_role = bool(re.search(r'role="', html))
            buttons_with_text = [b for b in soup.find_all("button") if b.get_text(strip=True) or b.get("aria-label")]
            buttons_total = soup.find_all("button")
            inaccessible_buttons = len(buttons_total) - len(buttons_with_text)
            form_labels = len(soup.find_all("label"))
            form_inputs = len(soup.find_all("input", attrs={"type": lambda t: t not in ["hidden", "submit", "button"]})) if soup.find_all("input") else 0
            unlabeled_inputs = max(0, form_inputs - form_labels)

            accessibility_pts = 50
            if has_lang: accessibility_pts += 15
            if has_aria: accessibility_pts += 10
            if has_role: accessibility_pts += 8
            if skip_link: accessibility_pts += 7
            if alt_ratio >= 1.0: accessibility_pts += 10
            elif alt_ratio >= 0.5: accessibility_pts += 5
            accessibility_pts -= min(20, inaccessible_buttons * 3)
            accessibility_pts -= min(15, unlabeled_inputs * 3)
            accessibility_score = max(10, min(100, accessibility_pts))

            if not has_lang:
                accessibility_issues.append({"title": "HTML lang attribute missing", "category": "accessibility", "severity": "warning", "description": "Screen readers need the lang attribute to use correct pronunciation."})
                recommendations.append("Add lang attribute to <html> tag (e.g. <html lang='en'>)")
            if inaccessible_buttons > 0:
                accessibility_issues.append({"title": f"{inaccessible_buttons} button(s) without accessible text", "category": "accessibility", "severity": "warning", "description": "Buttons need visible text or aria-label for screen reader users."})
            if unlabeled_inputs > 0:
                accessibility_issues.append({"title": f"{unlabeled_inputs} form input(s) without labels", "category": "accessibility", "severity": "warning", "description": "Form inputs must have associated <label> elements for accessibility."})
                recommendations.append(f"Add <label> elements to {unlabeled_inputs} form input(s)")

            # ── Tech Stack Detection ──────────────────────────────────────────
            tech_map = {
                "WordPress": ["wp-content", "wp-includes", "wordpress"],
                "Shopify": ["shopify", "cdn.shopify.com"],
                "Wix": ["wix.com", "wixsite.com", "wixstatic.com"],
                "Squarespace": ["squarespace.com", "sqsp.net"],
                "Webflow": ["webflow.com", "webflow.io"],
                "React": ["react.min.js", "__react", "react-dom", "data-reactroot"],
                "Vue.js": ["vue.min.js", "__vue__", "v-app", "vue-router"],
                "Angular": ["ng-version", "angular.min.js", "ng-app"],
                "Next.js": ["__next", "_next/static", "next.js"],
                "Nuxt.js": ["__nuxt", "_nuxt"],
                "jQuery": ["jquery.min.js", "jquery-"],
                "Bootstrap": ["bootstrap.min.css", "bootstrap.css", "bootstrap.min.js"],
                "Tailwind CSS": ["tailwind.css", "tailwindcss"],
                "Font Awesome": ["font-awesome", "fontawesome"],
                "Google Analytics": ["google-analytics.com", "gtag/js", "analytics.js"],
                "Google Tag Manager": ["googletagmanager.com"],
                "Facebook Pixel": ["connect.facebook.net", "fbq("],
                "HubSpot": ["hs-scripts.com", "hubspot"],
                "Mailchimp": ["mailchimp.com", "chimpstatic.com"],
                "Stripe": ["stripe.com/v3", "stripe.js"],
                "PayPal": ["paypal.com/sdk", "paypalobjects.com"],
                "Cloudflare": ["cloudflare", "__cflb", "cf-ray"],
                "reCAPTCHA": ["recaptcha", "grecaptcha"],
                "PHP": ["php"],
                "Laravel": ["laravel"],
                "Django": ["django", "csrfmiddlewaretoken"],
                "Ruby on Rails": ["rails", "authenticity_token"],
            }
            for tech, patterns in tech_map.items():
                if any(p in html_lower for p in patterns):
                    tech_stack.append(tech)

            # ── Content Score ─────────────────────────────────────────────────
            content_pts = 30
            if word_count >= 300: content_pts += 20
            if word_count >= 800: content_pts += 10
            if len(img_tags) >= 1: content_pts += 10
            if len(img_tags) >= 3: content_pts += 5
            if structured_data: content_pts += 10
            if has_og: content_pts += 5
            if has_keywords: content_pts += 5
            if len(h2_tags) >= 2: content_pts += 5
            content_score = min(100, content_pts)

            # ── Branding Score ────────────────────────────────────────────────
            branding_pts = 40
            if has_favicon: branding_pts += 15
            if has_custom_fonts: branding_pts += 10
            if has_og_image: branding_pts += 10
            if has_social: branding_pts += 10
            if has_hero: branding_pts += 10
            if has_animations: branding_pts += 5
            branding_score = min(100, branding_pts)

            # ── Conversion Score ──────────────────────────────────────────────
            conversion_pts = 20
            if has_cta: conversion_pts += 25
            if has_contact_form: conversion_pts += 20
            if has_phone: conversion_pts += 10
            if has_reviews: conversion_pts += 10
            if has_live_chat: conversion_pts += 10
            if has_map: conversion_pts += 5
            conversion_score = min(100, conversion_pts)

            # ── Overall Score (weighted) ──────────────────────────────────────
            overall = int(
                seo_score * 0.20 +
                mobile_score * 0.15 +
                speed_score * 0.15 +
                ui_score * 0.15 +
                ux_score * 0.10 +
                security_score * 0.10 +
                content_score * 0.10 +
                conversion_score * 0.05
            )

            # ── Convert recommendations to structured dicts ───────────────────
            recs_dicts: List[Dict[str, Any]] = []
            for i, rec_text in enumerate(recommendations):
                # Determine category from text
                cat = "general"
                if any(k in rec_text.lower() for k in ["seo", "title", "meta", "keyword", "h1", "canonical", "open graph", "structured", "alt text", "word", "content"]):
                    cat = "seo"
                elif any(k in rec_text.lower() for k in ["mobile", "viewport", "responsive", "media quer"]):
                    cat = "mobile"
                elif any(k in rec_text.lower() for k in ["speed", "load", "async", "defer", "minif", "lazy", "cache"]):
                    cat = "speed"
                elif any(k in rec_text.lower() for k in ["secur", "https", "ssl", "hsts", "csp", "header", "xss"]):
                    cat = "security"
                elif any(k in rec_text.lower() for k in ["access", "aria", "label", "screen reader", "lang", "skip"]):
                    cat = "accessibility"
                elif any(k in rec_text.lower() for k in ["contact", "cta", "form", "call-to-action", "review", "testimonial", "social", "phone", "nav", "footer", "map"]):
                    cat = "ux"
                elif any(k in rec_text.lower() for k in ["favicon", "font", "brand", "design"]):
                    cat = "branding"
                recs_dicts.append({
                    "category": cat,
                    "priority": "high" if i < 3 else ("medium" if i < 7 else "low"),
                    "title": rec_text[:80],
                    "description": rec_text,
                })

            # ── AI Analysis as structured dict ────────────────────────────────
            critical_count = sum(1 for i in seo_issues + accessibility_issues if i.get("severity") == "critical")
            warning_count = sum(1 for i in seo_issues + accessibility_issues if i.get("severity") == "warning")

            strengths: List[str] = []
            weaknesses: List[str] = []
            if seo_score >= 70: strengths.append(f"Good SEO foundation ({seo_score}/100)")
            if mobile_score >= 70: strengths.append(f"Mobile-friendly design ({mobile_score}/100)")
            if speed_score >= 70: strengths.append(f"Fast page load ({speed_score}/100)")
            if security_score >= 70: strengths.append(f"Secure HTTPS setup ({security_score}/100)")
            if has_social: strengths.append("Social media presence established")
            if has_reviews: strengths.append("Customer reviews/testimonials present")
            if not strengths: strengths.append("Basic web presence established")

            if seo_score < 50: weaknesses.append(f"Poor SEO — only {seo_score}/100")
            if mobile_score < 50: weaknesses.append(f"Not mobile-optimized ({mobile_score}/100)")
            if speed_score < 50: weaknesses.append(f"Slow website — {ttfb_ms}ms response time")
            if security_score < 50: weaknesses.append(f"Security issues detected ({security_score}/100)")
            if not has_contact_form: weaknesses.append("No contact form — missing lead capture")
            if not weaknesses: weaknesses.append("Minor optimizations possible")

            opportunities: List[str] = []
            if seo_score < 70: opportunities.append("SEO improvements could boost search visibility by 30-50%")
            if not has_cta: opportunities.append("Adding CTAs could increase conversions by 20-40%")
            if not has_reviews: opportunities.append("Adding testimonials typically increases trust and conversions")
            if mobile_score < 70: opportunities.append("Mobile optimization could capture more smartphone traffic")
            if not opportunities: opportunities.append("Fine-tune performance for competitive advantage")

            ai_analysis = {
                "executive_summary": (
                    f"Website audit completed for {url}. Overall score: {overall}/100. "
                    f"Found {critical_count} critical issue{'s' if critical_count != 1 else ''} and "
                    f"{warning_count} warning{'s' if warning_count != 1 else ''}. "
                    + ("Significant improvements needed." if overall < 50 else
                       "Good foundation with room for improvement." if overall < 75 else
                       "Strong digital presence with minor optimizations possible.")
                ),
                "strengths": strengths[:3],
                "weaknesses": weaknesses[:3],
                "opportunities": opportunities[:3],
                "estimated_value": (
                    "high" if overall < 40 else
                    "medium" if overall < 65 else "low"
                ),
                "scores_summary": {
                    "seo": seo_score,
                    "mobile": mobile_score,
                    "speed": speed_score,
                    "ui": ui_score,
                    "ux": ux_score,
                    "security": security_score,
                    "content": content_score,
                    "branding": branding_score,
                    "conversion": conversion_score,
                    "overall": overall,
                },
            }

            perf_metrics = {
                "ttfb_ms": ttfb_ms,
                "page_size_kb": round(page_size_kb, 1),
                "word_count": word_count,
                "image_count": len(img_tags),
                "link_count": len(all_links),
                "internal_links": len(internal_links),
                "external_links": len(external_links),
                "render_blocking_scripts": render_blocking_js,
                "render_blocking_css": render_blocking_css,
                "h1_count": len(h1_tags),
                "h2_count": len(h2_tags),
                "h3_count": len(h3_tags),
                "has_ssl": is_https,
                "has_hsts": hsts,
                "has_csp": csp,
                "has_viewport": has_viewport,
                "has_og_tags": has_og,
                "has_structured_data": structured_data,
                "has_favicon": has_favicon,
                "has_contact_form": has_contact_form,
                "has_social_links": has_social,
                "has_phone": has_phone,
                "has_reviews": has_reviews,
                "status_code": status_code,
                "final_url": final_url,
            }

            audit.status = AuditStatus.completed
            audit.overall_score = float(overall)
            audit.seo_score = float(seo_score)
            audit.mobile_score = float(mobile_score)
            audit.speed_score = float(speed_score)
            audit.ui_score = float(ui_score)
            audit.ux_score = float(ux_score)
            audit.security_score = float(security_score)
            audit.accessibility_score = float(accessibility_score)
            audit.content_score = float(content_score)
            audit.branding_score = float(branding_score)
            audit.conversion_score = float(conversion_score)
            audit.tech_stack = [{"name": t, "category": "detected"} for t in tech_stack]
            audit.recommendations = recs_dicts
            audit.seo_issues = seo_issues
            audit.accessibility_issues = accessibility_issues
            audit.performance_metrics = perf_metrics
            audit.ai_analysis = ai_analysis
            audit.completed_at = datetime.now(timezone.utc)

            # Update business scores + extract contact info from HTML
            biz_stmt = select(Business).where(Business.id == _uuid.UUID(business_id))
            biz_row = await session.execute(biz_stmt)
            biz = biz_row.scalar_one_or_none()
            if biz:
                biz.overall_score = float(overall)
                biz.opportunity_score = round(max(0.0, 100.0 - overall) * 0.8 + (20.0 if not biz.has_website else 0.0), 1)
                biz.priority_score = round(
                    (max(0.0, 100.0 - overall) * 0.5) +
                    (30.0 if not biz.has_website else 0.0) +
                    (10.0 if overall < 40 else 5.0 if overall < 60 else 0.0),
                    1
                )
                # Compute revenue potential using scoring engine
                try:
                    from app.engines.scoring.scoring_engine import ScoringEngine
                    _engine = ScoringEngine()
                    _rev = _engine.estimate_revenue_potential(biz, audit)
                    biz.revenue_potential = float((_rev["min"] + _rev["max"]) / 2.0)
                except Exception:
                    # Fallback: rough estimate based on industry
                    industry_lower = (biz.industry or biz.category or "").lower()
                    if any(k in industry_lower for k in ("legal", "medical", "health", "finance", "real estate")):
                        biz.revenue_potential = 15000.0
                    elif any(k in industry_lower for k in ("restaurant", "hotel", "retail", "salon")):
                        biz.revenue_potential = 6000.0
                    else:
                        biz.revenue_potential = 8000.0
                biz.last_audited_at = datetime.now(timezone.utc)
                biz.audit_count = (biz.audit_count or 0) + 1

                # Extract email / phone from page HTML if not already set
                try:
                    from app.engines.contact.contact_extractor import ContactExtractor, EXCLUDED_EMAILS
                    extractor = ContactExtractor()
                    contacts = extractor.extract_from_html(html, url)
                    # Pick best email (highest confidence, skip generic ones)
                    if not biz.email:
                        for c in sorted(contacts, key=lambda x: x.confidence_score, reverse=True):
                            if c.email:
                                local = c.email.split("@")[0].lower()
                                if local not in EXCLUDED_EMAILS:
                                    biz.email = c.email
                                    break
                        # Fallback: accept generic emails if that's all we have
                        if not biz.email:
                            for c in contacts:
                                if c.email:
                                    biz.email = c.email
                                    break
                    # Extract phone if not set (only international format for WhatsApp)
                    if not biz.phone:
                        for c in contacts:
                            if c.phone and c.phone.startswith("+"):
                                biz.phone = c.phone
                                break
                    # Extract social profiles
                    existing_socials = biz.social_profiles or {}
                    for c in contacts:
                        for platform, link in (c.social_profiles or {}).items():
                            if platform not in existing_socials:
                                existing_socials[platform] = link
                    if existing_socials:
                        biz.social_profiles = existing_socials
                except Exception:
                    pass  # contact extraction is best-effort

            await session.commit()

        except Exception as exc:
            audit.status = AuditStatus.failed
            audit.error_message = str(exc)
            audit.completed_at = datetime.now(timezone.utc)
            await session.commit()


# ---------------------------------------------------------------------------
# DELETE /audits/{id}
# ---------------------------------------------------------------------------


@router.delete("/{audit_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_audit(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> None:
    """Delete an audit report (screenshots cascade)."""
    audit = await _get_audit_or_404(audit_id, db)
    await db.delete(audit)
    await db.commit()


# ---------------------------------------------------------------------------
# GET /audits/{id}/screenshots
# ---------------------------------------------------------------------------


@router.get("/{audit_id}/screenshots", status_code=status.HTTP_200_OK)
async def list_audit_screenshots(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return all screenshots captured during an audit run."""
    await _get_audit_or_404(audit_id, db)

    stmt = (
        select(Screenshot)
        .where(Screenshot.audit_id == audit_id)
        .order_by(Screenshot.captured_at.desc())
    )
    rows = await db.execute(stmt)
    screenshots = rows.scalars().all()

    return {
        "audit_id": str(audit_id),
        "items": [_screenshot_to_dict(s) for s in screenshots],
        "total": len(screenshots),
    }
