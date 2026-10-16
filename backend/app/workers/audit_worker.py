"""
Audit worker tasks.

Tasks
-----
run_audit_job(business_id, config)
    Run the full audit pipeline for one business: website detection, scraping,
    scoring, screenshot capture, and AI analysis.  Saves an AuditReport and
    updates the Business's score fields.

run_bulk_audit(business_ids)
    Fan-out: queue one run_audit_job per business_id.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery import Task
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger
from sqlalchemy import select, update

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business, WebsiteStatus
from app.models.screenshot import Screenshot, Viewport
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


_SCREENSHOT_VIEWPORTS = {
    Viewport.desktop: {"width": 1280, "height": 900},
    Viewport.mobile: {"width": 390, "height": 844},
}


# ---------------------------------------------------------------------------
# Task: run_audit_job
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.workers.audit_worker.run_audit_job",
    max_retries=2,
    default_retry_delay=180,
    queue="audit-queue",
    # Audits can be slow (screenshots + AI)
    soft_time_limit=480,
    time_limit=540,
)
def run_audit_job(
    self: Task,
    business_id: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run a full audit for the given *business_id*.

    Parameters
    ----------
    business_id:
        UUID string of the Business to audit.
    config:
        Optional dict with audit overrides, e.g.::

            {
                "capture_screenshots": True,
                "run_ai_analysis": True,
                "viewport": "desktop",
            }
    """
    return _run_async(_run_audit_job_async(self, business_id, config or {}))


async def _run_audit_job_async(
    task: Task,
    business_id: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    capture_screenshots: bool = config.get("capture_screenshots", True)
    run_ai: bool = config.get("run_ai_analysis", True)

    async with AsyncSessionLocal() as session:
        biz_stmt = select(Business).where(Business.id == uuid.UUID(business_id))
        biz_row = await session.execute(biz_stmt)
        business: Optional[Business] = biz_row.scalar_one_or_none()

        if business is None:
            logger.error("audit_job.business_not_found", business_id=business_id)
            return {"status": "not_found", "business_id": business_id}

    # -- Create an AuditReport row in pending state --
    audit_id = await _create_audit_report(
        business_id=uuid.UUID(business_id),
        website_url=business.website_url,
    )

    try:
        await _set_audit_status(audit_id, AuditStatus.running)

        url = business.website_url
        if not url:
            # Try to discover website
            from app.engines.audit.website_detector import WebsiteDetector

            detector = WebsiteDetector()
            discovered = await detector.discover_website(business.name, business.city or "")
            if discovered:
                url = discovered
                await _update_business_url(uuid.UUID(business_id), url)

        if not url:
            raise ValueError(f"No website URL found for business {business_id}")

        # -- Step 1: Scrape the website --
        from app.engines.scraper.scraper_engine import ScraperConfig, ScraperEngine

        scraper_config = ScraperConfig(
            timeout_ms=settings.PLAYWRIGHT_TIMEOUT,
            headless=settings.PLAYWRIGHT_HEADLESS,
            capture_html=True,
        )

        scraped_data = None
        async with ScraperEngine() as scraper:
            scraped_data = await scraper.scrape_website(url, scraper_config)

        # -- Step 2: Capture screenshots --
        screenshot_desktop_url: Optional[str] = None
        screenshot_mobile_url: Optional[str] = None

        if capture_screenshots and scraped_data and not scraped_data.error:
            desktop_path, mobile_path = await _capture_screenshots(
                url=url,
                audit_id=audit_id,
                business_id=uuid.UUID(business_id),
            )
            if desktop_path:
                screenshot_desktop_url = str(desktop_path)
            if mobile_path:
                screenshot_mobile_url = str(mobile_path)

        # -- Step 3: Build scores from scraped data --
        scores = _compute_scores(scraped_data)

        # -- Step 4: AI analysis (optional) --
        ai_analysis: Optional[Dict[str, Any]] = None
        if run_ai and scraped_data:
            ai_analysis = await _run_ai_analysis(scraped_data, business)

        # -- Step 5: Save audit report --
        tech_stack_list = (
            scraped_data.tech_stack.detected_stack
            if scraped_data and scraped_data.tech_stack
            else []
        )

        await _save_audit_results(
            audit_id=audit_id,
            business_id=uuid.UUID(business_id),
            scores=scores,
            screenshot_desktop_url=screenshot_desktop_url,
            screenshot_mobile_url=screenshot_mobile_url,
            tech_stack=tech_stack_list,
            ai_analysis=ai_analysis,
            scraped_data=scraped_data,
        )

        logger.info(
            "audit_job.completed",
            business_id=business_id,
            audit_id=str(audit_id),
            overall_score=scores.get("overall"),
        )
        return {
            "status": "completed",
            "business_id": business_id,
            "audit_id": str(audit_id),
            "scores": scores,
        }

    except Exception as exc:
        logger.exception("audit_job.failed", business_id=business_id, error=str(exc))
        await _fail_audit(audit_id, str(exc))
        try:
            raise task.retry(exc=exc)
        except MaxRetriesExceededError:
            return {
                "status": "failed",
                "business_id": business_id,
                "audit_id": str(audit_id),
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Task: run_bulk_audit
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.workers.audit_worker.run_bulk_audit",
    queue="audit-queue",
)
def run_bulk_audit(
    business_ids: List[str],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Queue individual audit tasks for each business in *business_ids*.

    Returns a mapping of business_id -> celery task_id.
    """
    config = config or {}
    queued: Dict[str, str] = {}

    for bid in business_ids:
        async_result = run_audit_job.apply_async(
            args=[bid],
            kwargs={"config": config},
            queue="audit-queue",
        )
        queued[bid] = async_result.id
        logger.info("bulk_audit.queued", business_id=bid, task_id=async_result.id)

    logger.info("bulk_audit.dispatch_done", count=len(queued))
    return {"queued": queued, "total": len(queued)}


# ---------------------------------------------------------------------------
# Private: screenshot capture
# ---------------------------------------------------------------------------


async def _capture_screenshots(
    url: str,
    audit_id: uuid.UUID,
    business_id: uuid.UUID,
) -> tuple[Optional[Path], Optional[Path]]:
    """Capture desktop and mobile screenshots. Returns (desktop_path, mobile_path)."""
    from playwright.async_api import async_playwright  # type: ignore

    desktop_path: Optional[Path] = None
    mobile_path: Optional[Path] = None
    screenshot_dir = settings.screenshot_path
    audit_dir = screenshot_dir / str(audit_id)
    audit_dir.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            try:
                for viewport, dims in _SCREENSHOT_VIEWPORTS.items():
                    context = await browser.new_context(
                        viewport=dims,
                        ignore_https_errors=True,
                    )
                    page = await context.new_page()
                    try:
                        await page.goto(
                            url,
                            timeout=settings.PLAYWRIGHT_TIMEOUT,
                            wait_until="domcontentloaded",
                        )
                        await page.wait_for_timeout(1500)
                        fname = f"{viewport.value}.png"
                        fpath = audit_dir / fname
                        await page.screenshot(path=str(fpath), full_page=False)

                        # Persist Screenshot record
                        width = dims["width"]
                        height = dims["height"]
                        file_size = fpath.stat().st_size if fpath.exists() else None
                        await _save_screenshot_record(
                            business_id=business_id,
                            audit_id=audit_id,
                            viewport=viewport,
                            file_path=str(fpath),
                            url=url,
                            width=width,
                            height=height,
                            file_size=file_size,
                        )

                        if viewport == Viewport.desktop:
                            desktop_path = fpath
                        else:
                            mobile_path = fpath

                    except Exception as page_exc:
                        logger.warning(
                            "screenshot.capture_failed",
                            viewport=viewport.value,
                            url=url,
                            error=str(page_exc),
                        )
                    finally:
                        await context.close()
            finally:
                await browser.close()
    except Exception as exc:
        logger.warning("screenshot.playwright_failed", url=url, error=str(exc))

    return desktop_path, mobile_path


# ---------------------------------------------------------------------------
# Private: scoring
# ---------------------------------------------------------------------------


def _compute_scores(scraped_data: Any) -> Dict[str, float]:
    """
    Derive simple heuristic scores from scraped data.
    Returns a dict with keys matching AuditReport score columns.
    """
    if scraped_data is None or scraped_data.error:
        return {}

    scores: Dict[str, float] = {}

    # SEO score heuristics
    seo = 50.0
    if scraped_data.title:
        seo += 10
        if 10 <= len(scraped_data.title) <= 60:
            seo += 5
    if scraped_data.meta_description:
        seo += 10
        if 50 <= len(scraped_data.meta_description) <= 160:
            seo += 5
    if scraped_data.headings.get("h1"):
        seo += 10
        if len(scraped_data.headings["h1"]) == 1:
            seo += 5
    if scraped_data.canonical_url:
        seo += 5
    seo = min(100.0, seo)
    scores["seo_score"] = round(seo, 1)

    # Mobile score: presence of viewport meta tag
    mobile = 50.0
    if scraped_data.meta_tags.get("viewport"):
        mobile += 30
    if scraped_data.tech_stack and any(
        t["name"] in ("Bootstrap", "Tailwind CSS")
        for t in (scraped_data.tech_stack.detected_stack or [])
    ):
        mobile += 20
    scores["mobile_score"] = round(min(100.0, mobile), 1)

    # Content score
    content = 40.0
    word_count = scraped_data.word_count or 0
    if word_count >= 300:
        content += 20
    if word_count >= 800:
        content += 15
    if scraped_data.images:
        content += 10
    if len(scraped_data.images) >= 3:
        content += 10
    if scraped_data.json_ld:
        content += 5
    scores["content_score"] = round(min(100.0, content), 1)

    # Conversion score: presence of forms + CTA links
    conversion = 50.0
    if scraped_data.forms:
        conversion += 20
    cta_keywords = ("contact", "sign up", "get started", "book", "buy", "subscribe", "demo")
    cta_links = [
        lnk for lnk in scraped_data.links
        if any(kw in lnk.text.lower() for kw in cta_keywords)
    ]
    if cta_links:
        conversion += 20
    if len(cta_links) >= 3:
        conversion += 10
    scores["conversion_score"] = round(min(100.0, conversion), 1)

    # Overall score
    score_vals = [v for v in scores.values() if v is not None]
    if score_vals:
        scores["overall_score"] = round(sum(score_vals) / len(score_vals), 1)

    return scores


# ---------------------------------------------------------------------------
# Private: AI analysis
# ---------------------------------------------------------------------------


async def _run_ai_analysis(
    scraped_data: Any, business: Business
) -> Optional[Dict[str, Any]]:
    """Call Claude to generate a brief strengths/weaknesses/opportunities summary."""
    try:
        import anthropic  # type: ignore

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = (
            f"Analyse the following website data for {business.name} and return a JSON object "
            f"with keys: strengths (list[str]), weaknesses (list[str]), opportunities (list[str]), "
            f"estimated_value (str - one of 'low'/'medium'/'high'), summary (str, 2-3 sentences).\n\n"
            f"Title: {scraped_data.title}\n"
            f"Description: {scraped_data.meta_description}\n"
            f"Word count: {scraped_data.word_count}\n"
            f"Forms: {len(scraped_data.forms)}\n"
            f"Tech stack: {[t['name'] for t in (scraped_data.tech_stack.detected_stack or [])]}\n"
            f"Headings: {scraped_data.headings}\n"
            f"Respond with valid JSON only."
        )

        response = await client.messages.create(
            model=settings.AI_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        import json
        text = response.content[0].text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)

    except Exception as exc:
        logger.warning("audit_job.ai_analysis_failed", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _create_audit_report(
    business_id: uuid.UUID,
    website_url: Optional[str],
) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        report = AuditReport(
            business_id=business_id,
            website_url=website_url,
            status=AuditStatus.pending,
        )
        session.add(report)
        await session.commit()
        return report.id


async def _set_audit_status(audit_id: uuid.UUID, status: AuditStatus) -> None:
    async with AsyncSessionLocal() as session:
        values: Dict[str, Any] = {"status": status}
        if status == AuditStatus.running:
            values["started_at"] = datetime.now(timezone.utc)
        await session.execute(
            update(AuditReport).where(AuditReport.id == audit_id).values(**values)
        )
        await session.commit()


async def _fail_audit(audit_id: uuid.UUID, error_message: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(AuditReport)
            .where(AuditReport.id == audit_id)
            .values(
                status=AuditStatus.failed,
                error_message=error_message,
                completed_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()


async def _save_audit_results(
    audit_id: uuid.UUID,
    business_id: uuid.UUID,
    scores: Dict[str, float],
    screenshot_desktop_url: Optional[str],
    screenshot_mobile_url: Optional[str],
    tech_stack: List[Dict[str, Any]],
    ai_analysis: Optional[Dict[str, Any]],
    scraped_data: Any,
) -> None:
    """Persist completed audit results and update Business score columns."""
    async with AsyncSessionLocal() as session:
        # Recommendations from scores
        recommendations = _build_recommendations(scores, scraped_data)

        # Performance metrics from scraped data
        perf_metrics: Dict[str, Any] = {}
        if scraped_data:
            perf_metrics = {
                "page_size_bytes": scraped_data.page_size_bytes,
                "response_time_ms": scraped_data.response_time_ms,
                "word_count": scraped_data.word_count,
                "image_count": len(scraped_data.images),
                "link_count": len(scraped_data.links),
                "form_count": len(scraped_data.forms),
            }

        await session.execute(
            update(AuditReport)
            .where(AuditReport.id == audit_id)
            .values(
                status=AuditStatus.completed,
                completed_at=datetime.now(timezone.utc),
                screenshot_desktop_url=screenshot_desktop_url,
                screenshot_mobile_url=screenshot_mobile_url,
                tech_stack=tech_stack,
                ai_analysis=ai_analysis,
                recommendations=recommendations,
                performance_metrics=perf_metrics,
                **{k: v for k, v in scores.items() if hasattr(AuditReport, k)},
            )
        )

        # Update Business score fields
        business_updates: Dict[str, Any] = {
            "last_audited_at": datetime.now(timezone.utc),
            "audit_count": Business.audit_count + 1,
        }
        if "overall_score" in scores:
            business_updates["overall_score"] = scores["overall_score"]

        await session.execute(
            update(Business)
            .where(Business.id == business_id)
            .values(**business_updates)
        )

        await session.commit()


async def _update_business_url(business_id: uuid.UUID, url: str) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(Business)
            .where(Business.id == business_id)
            .values(website_url=url, has_website=True, website_status=WebsiteStatus.active)
        )
        await session.commit()


async def _save_screenshot_record(
    business_id: uuid.UUID,
    audit_id: uuid.UUID,
    viewport: Viewport,
    file_path: str,
    url: str,
    width: int,
    height: int,
    file_size: Optional[int],
) -> None:
    async with AsyncSessionLocal() as session:
        record = Screenshot(
            business_id=business_id,
            audit_id=audit_id,
            viewport=viewport,
            file_path=file_path,
            url=url,
            width=width,
            height=height,
            file_size=file_size,
            captured_at=datetime.now(timezone.utc),
        )
        session.add(record)
        await session.commit()


def _build_recommendations(
    scores: Dict[str, float],
    scraped_data: Any,
) -> List[Dict[str, Any]]:
    """Generate actionable recommendations based on scores."""
    recs: List[Dict[str, Any]] = []

    if scores.get("seo_score", 100) < 70:
        recs.append({
            "category": "seo",
            "priority": "high",
            "title": "Improve SEO fundamentals",
            "description": (
                "Ensure the page has a unique <title> (10–60 chars), a meta description "
                "(50–160 chars), and a single H1 heading."
            ),
        })

    if scores.get("mobile_score", 100) < 70:
        recs.append({
            "category": "mobile",
            "priority": "high",
            "title": "Add a responsive viewport meta tag",
            "description": (
                'Include <meta name="viewport" content="width=device-width, initial-scale=1"> '
                "and use a responsive CSS framework."
            ),
        })

    if scores.get("content_score", 100) < 60:
        recs.append({
            "category": "content",
            "priority": "medium",
            "title": "Increase page content depth",
            "description": (
                "Pages with 300–800+ words perform better in search and build visitor trust."
            ),
        })

    if scores.get("conversion_score", 100) < 60:
        recs.append({
            "category": "conversion",
            "priority": "medium",
            "title": "Add clear calls-to-action",
            "description": (
                "Include at least one prominent CTA (contact form, booking link, or sign-up button)."
            ),
        })

    if scraped_data and not scraped_data.meta_tags.get("viewport"):
        recs.append({
            "category": "mobile",
            "priority": "high",
            "title": "Missing viewport meta tag",
            "description": "The page is likely not mobile-responsive.",
        })

    return recs
