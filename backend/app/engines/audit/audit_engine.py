"""
AuditEngine — orchestrates all sub-analysers to produce a complete AuditReport.

Usage::

    engine = AuditEngine()
    report = await engine.run_audit(business, audit_id, db_session)
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business, WebsiteStatus
from app.models.screenshot import Screenshot, Viewport

from app.engines.audit.accessibility_analyzer import AccessibilityAnalyzer
from app.engines.audit.content_analyzer import ContentAnalyzer
from app.engines.audit.performance_analyzer import PerformanceAnalyzer
from app.engines.audit.screenshot_engine import ScreenshotEngine
from app.engines.audit.security_analyzer import SecurityAnalyzer
from app.engines.audit.seo_analyzer import SEOAnalyzer
from app.engines.audit.ui_ux_analyzer import UIUXAnalyzer
from app.engines.audit.website_detector import WebsiteDetector, WebsiteStatusResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class AuditConfig:
    """
    Runtime configuration for the audit engine.

    Attributes
    ----------
    screenshot_dir:
        Where to persist captured screenshots.
    screenshot_base_url:
        Public URL prefix for screenshot links.
    timeout_seconds:
        HTTP / Playwright timeout (seconds).
    playwright_headless:
        Run browser headlessly.
    capture_screenshots:
        Whether to run the screenshot capture step.
    run_ai_analysis:
        Whether to call the AI (Claude) analysis step.
    anthropic_api_key:
        Anthropic API key; falls back to settings.ANTHROPIC_API_KEY.
    ai_model:
        Claude model identifier.
    score_weights:
        Mapping of category -> weight used to compute the overall score.
        Values should sum to 1.0 (or will be normalised).
    """

    screenshot_dir: str = ""
    screenshot_base_url: str = ""
    timeout_seconds: float = 30.0
    playwright_headless: bool = True
    capture_screenshots: bool = True
    run_ai_analysis: bool = True
    anthropic_api_key: str = ""
    ai_model: str = ""
    score_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "seo": 0.20,
            "accessibility": 0.10,
            "performance": 0.20,
            "security": 0.15,
            "ui_ux": 0.20,
            "content": 0.15,
        }
    )

    def __post_init__(self) -> None:
        if not self.screenshot_dir:
            self.screenshot_dir = settings.SCREENSHOT_DIR
        if not self.anthropic_api_key:
            self.anthropic_api_key = settings.ANTHROPIC_API_KEY
        if not self.ai_model:
            self.ai_model = settings.AI_MODEL
        self.playwright_headless = settings.PLAYWRIGHT_HEADLESS
        self.timeout_seconds = settings.PLAYWRIGHT_TIMEOUT / 1000


# ---------------------------------------------------------------------------
# Internal page-data helper
# ---------------------------------------------------------------------------


@dataclass
class PageData:
    """Raw data fetched from the page before analysis sub-tasks are run."""

    url: str
    final_url: str
    html: str
    response_headers: Dict[str, str]
    status_code: int
    response_time_ms: float


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class AuditEngine:
    """
    Orchestrate a full website audit.

    Parameters
    ----------
    config:
        Optional ``AuditConfig`` instance; defaults are constructed from
        ``settings`` when omitted.
    """

    def __init__(self, config: Optional[AuditConfig] = None) -> None:
        self.config = config or AuditConfig()
        self._detector = WebsiteDetector(timeout=self.config.timeout_seconds)
        self._screenshot_engine = ScreenshotEngine(
            screenshot_dir=self.config.screenshot_dir,
            base_url=self.config.screenshot_base_url,
            timeout_ms=int(self.config.timeout_seconds * 1000),
            headless=self.config.playwright_headless,
        )
        self._seo = SEOAnalyzer(timeout=self.config.timeout_seconds)
        self._accessibility = AccessibilityAnalyzer()
        self._performance = PerformanceAnalyzer(
            timeout_ms=int(self.config.timeout_seconds * 1000),
            headless=self.config.playwright_headless,
        )
        self._security = SecurityAnalyzer(timeout=self.config.timeout_seconds)
        self._ui_ux = UIUXAnalyzer()
        self._content = ContentAnalyzer()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run_audit(
        self,
        business: Business,
        audit_id: uuid.UUID,
        db_session: AsyncSession,
    ) -> AuditReport:
        """
        Run a complete audit for *business* and persist all results to the
        existing ``AuditReport`` row identified by *audit_id*.

        Returns the updated ``AuditReport`` ORM object.
        """
        # Reload the report row to update it
        from sqlalchemy import select

        result = await db_session.execute(
            select(AuditReport).where(AuditReport.id == audit_id)
        )
        audit_report: Optional[AuditReport] = result.scalar_one_or_none()
        if audit_report is None:
            raise ValueError(f"AuditReport {audit_id} not found.")

        audit_report.status = AuditStatus.running
        audit_report.started_at = datetime.now(timezone.utc)
        await db_session.commit()

        try:
            final_report = await self._execute_audit(
                business=business,
                audit_report=audit_report,
                db_session=db_session,
            )
            final_report.status = AuditStatus.completed
            final_report.completed_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("Audit failed for business %s: %s", business.id, exc)
            audit_report.status = AuditStatus.failed
            audit_report.error_message = str(exc)[:2000]
            audit_report.completed_at = datetime.now(timezone.utc)
            await db_session.commit()
            return audit_report

        await db_session.commit()
        return final_report

    # ------------------------------------------------------------------
    # Internal: execute all analysis steps
    # ------------------------------------------------------------------

    async def _execute_audit(
        self,
        business: Business,
        audit_report: AuditReport,
        db_session: AsyncSession,
    ) -> AuditReport:
        # ---- Step 1: Resolve URL -----------------------------------
        url = business.website_url or ""
        if not url and business.name:
            logger.info("No URL for %s; attempting discovery", business.name)
            discovered = await self._detector.discover_website(
                business.name, business.city or ""
            )
            if discovered:
                url = discovered
                business.website_url = url

        if not url:
            audit_report.website_url = None
            _mark_no_website(audit_report)
            await db_session.commit()
            return audit_report

        # ---- Step 2: Website detection ----------------------------
        logger.info("Detecting website: %s", url)
        website_status: WebsiteStatusResult = await self._detector.detect(url)
        audit_report.website_url = website_status.final_url

        if website_status.status in ("missing", "error"):
            _mark_no_website(audit_report)
            audit_report.error_message = website_status.error or "Website not reachable"
            return audit_report

        # Propagate website status back to Business model
        _sync_website_status(business, website_status)

        if website_status.status in ("parked", "inactive"):
            # Still run a partial audit but flag as parked/inactive
            logger.info("Website is %s: %s", website_status.status, url)

        effective_url = website_status.final_url

        # ---- Step 3: Fetch page data ------------------------------
        logger.info("Fetching page data: %s", effective_url)
        page_data = await self._fetch_page_data(effective_url)

        # ---- Step 4: Screenshots (concurrent) --------------------
        screenshot_paths: Dict[str, str] = {}
        if self.config.capture_screenshots and website_status.status == "active":
            logger.info("Capturing screenshots: %s", effective_url)
            screenshot_paths = await self._capture_screenshots(
                url=effective_url,
                business=business,
                audit_report=audit_report,
                db_session=db_session,
            )
            if "desktop" in screenshot_paths:
                audit_report.screenshot_desktop_url = screenshot_paths["desktop"]
            if "mobile" in screenshot_paths:
                audit_report.screenshot_mobile_url = screenshot_paths["mobile"]

        # ---- Step 5: Run all analyses concurrently ---------------
        logger.info("Running analysis suite: %s", effective_url)
        (
            seo_report,
            accessibility_report,
            performance_report,
            security_report,
            ui_ux_report,
            content_report,
        ) = await asyncio.gather(
            self._seo.analyze(effective_url, page_data.html, {}),
            self._accessibility.analyze(effective_url, page_data.html),
            self._performance.analyze(effective_url),
            self._security.analyze(
                effective_url,
                page_data.html,
                page_data.response_headers,
            ),
            self._ui_ux_with_screenshot(
                page_data.html,
                effective_url,
                screenshot_paths.get("desktop"),
            ),
            self._content.analyze(effective_url, page_data.html),
            return_exceptions=True,
        )

        # ---- Step 6: Store analysis results ----------------------
        # SEO
        if not isinstance(seo_report, Exception):
            audit_report.seo_score = seo_report.score
            audit_report.seo_issues = [i.to_dict() for i in seo_report.issues]
        else:
            logger.warning("SEO analysis error: %s", seo_report)
            audit_report.seo_score = 0.0

        # Accessibility
        if not isinstance(accessibility_report, Exception):
            audit_report.accessibility_score = accessibility_report.score
            audit_report.accessibility_issues = [
                v.to_dict() for v in accessibility_report.violations
            ]
        else:
            logger.warning("Accessibility analysis error: %s", accessibility_report)
            audit_report.accessibility_score = 0.0

        # Performance
        if not isinstance(performance_report, Exception):
            audit_report.speed_score = performance_report.score
            audit_report.performance_metrics = performance_report.metrics
        else:
            logger.warning("Performance analysis error: %s", performance_report)
            audit_report.speed_score = 0.0

        # Security
        if not isinstance(security_report, Exception):
            audit_report.security_score = security_report.score
        else:
            logger.warning("Security analysis error: %s", security_report)
            audit_report.security_score = 0.0

        # UI/UX
        if not isinstance(ui_ux_report, Exception):
            audit_report.ui_score = ui_ux_report.score
            audit_report.ux_score = ui_ux_report.score  # share the single score
            mobile_ok = ui_ux_report.metadata.get("has_viewport_meta", False)
            audit_report.mobile_score = 80.0 if mobile_ok else 30.0
            # Extract tech stack
            tech = ui_ux_report.metadata.get("js_frameworks", [])
            css_fw = ui_ux_report.metadata.get("css_frameworks", [])
            audit_report.tech_stack = [
                {"name": t, "category": "js_framework"} for t in tech
            ] + [
                {"name": t, "category": "css_framework"} for t in css_fw
            ]
        else:
            logger.warning("UI/UX analysis error: %s", ui_ux_report)
            audit_report.ui_score = 0.0
            audit_report.ux_score = 0.0

        # Content
        if not isinstance(content_report, Exception):
            audit_report.content_score = content_report.score
            # Branding: approximate from content signals
            has_social = bool(
                content_report.metadata.get("social_links")
            )
            has_copyright = content_report.metadata.get("has_copyright", False)
            audit_report.branding_score = (
                75.0
                + (10.0 if has_social else 0.0)
                + (5.0 if has_copyright else 0.0)
            )
            # Conversion: approximate from UI/UX CTA data
            if not isinstance(ui_ux_report, Exception):
                cta_count = ui_ux_report.metadata.get("cta_count", 0)
                audit_report.conversion_score = min(
                    100.0, 40.0 + min(cta_count, 6) * 10.0
                )
            else:
                audit_report.conversion_score = 30.0
        else:
            logger.warning("Content analysis error: %s", content_report)
            audit_report.content_score = 0.0

        # ---- Step 7: Aggregate score -----------------------------
        audit_report.overall_score = self._calculate_overall_score(audit_report)

        # ---- Step 8: Merge all recommendations -------------------
        all_recs: List[Dict[str, Any]] = []
        for rep in [
            seo_report,
            accessibility_report,
            performance_report,
            security_report,
            ui_ux_report,
            content_report,
        ]:
            if not isinstance(rep, Exception) and hasattr(rep, "recommendations"):
                all_recs.extend(rep.recommendations)
        all_recs.sort(key=lambda r: r.get("priority", 99))
        audit_report.recommendations = all_recs[:50]  # cap at 50

        # ---- Step 9: AI analysis (optional) ----------------------
        if (
            self.config.run_ai_analysis
            and self.config.anthropic_api_key
            and website_status.status == "active"
        ):
            logger.info("Running AI analysis: %s", effective_url)
            try:
                audit_report.ai_analysis = await self._run_ai_analysis(
                    business=business,
                    audit_report=audit_report,
                    seo_report=seo_report if not isinstance(seo_report, Exception) else None,
                    performance_report=performance_report if not isinstance(performance_report, Exception) else None,
                    security_report=security_report if not isinstance(security_report, Exception) else None,
                    content_report=content_report if not isinstance(content_report, Exception) else None,
                )
            except Exception as exc:
                logger.warning("AI analysis failed: %s", exc)

        # Update business scoring fields
        business.last_audited_at = datetime.now(timezone.utc)
        if audit_report.overall_score is not None:
            business.overall_score = audit_report.overall_score
        business.audit_count = (business.audit_count or 0) + 1

        return audit_report

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    async def _fetch_page_data(self, url: str) -> PageData:
        """HTTP GET the page and return a PageData bundle."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        import time

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.config.timeout_seconds,
            verify=False,
            headers=headers,
        ) as client:
            t0 = time.perf_counter()
            response = await client.get(url)
            elapsed_ms = (time.perf_counter() - t0) * 1000

        return PageData(
            url=url,
            final_url=str(response.url),
            html=response.text,
            response_headers=dict(response.headers),
            status_code=response.status_code,
            response_time_ms=round(elapsed_ms, 1),
        )

    async def _capture_screenshots(
        self,
        url: str,
        business: Business,
        audit_report: AuditReport,
        db_session: AsyncSession,
    ) -> Dict[str, str]:
        """
        Capture all viewports and persist Screenshot ORM rows.
        Returns dict of viewport -> file_url.
        """
        try:
            captures = await self._screenshot_engine.capture_all(url)
        except Exception as exc:
            logger.warning("Screenshot capture failed: %s", exc)
            return {}

        _VIEWPORT_MAP = {
            "desktop": Viewport.desktop,
            "mobile": Viewport.mobile,
            "tablet": Viewport.tablet,
            "full_page": Viewport.full_page,
        }
        result: Dict[str, str] = {}
        for viewport_name, capture in captures.items():
            if capture.error or not capture.file_path:
                continue
            screenshot = Screenshot(
                business_id=business.id,
                audit_id=audit_report.id,
                viewport=_VIEWPORT_MAP[viewport_name],
                file_path=capture.file_path,
                file_url=capture.file_url,
                file_size=capture.file_size,
                width=capture.width,
                height=capture.height,
                captured_at=capture.captured_at,
                url=url,
            )
            db_session.add(screenshot)
            result[viewport_name] = capture.file_url

        return result

    async def _ui_ux_with_screenshot(
        self,
        html: str,
        url: str,
        screenshot_path: Optional[str],
    ):
        """Run UIUXAnalyzer with optional screenshot path."""
        analyzer = UIUXAnalyzer(screenshot_path=screenshot_path)
        return await analyzer.analyze(html, url)

    # ------------------------------------------------------------------
    # Score calculation
    # ------------------------------------------------------------------

    def _calculate_overall_score(self, report: AuditReport) -> float:
        """Weighted average of category scores."""
        weights = self.config.score_weights
        total_weight = sum(weights.values())

        score_map = {
            "seo": report.seo_score,
            "accessibility": report.accessibility_score,
            "performance": report.speed_score,
            "security": report.security_score,
            "ui_ux": report.ui_score,
            "content": report.content_score,
        }

        weighted_sum = 0.0
        effective_weight = 0.0
        for key, weight in weights.items():
            value = score_map.get(key)
            if value is not None:
                weighted_sum += value * weight
                effective_weight += weight

        if effective_weight == 0:
            return 0.0
        return round(weighted_sum / effective_weight, 1)

    # ------------------------------------------------------------------
    # AI analysis via Claude
    # ------------------------------------------------------------------

    async def _run_ai_analysis(
        self,
        business: Business,
        audit_report: AuditReport,
        seo_report: Any,
        performance_report: Any,
        security_report: Any,
        content_report: Any,
    ) -> Dict[str, Any]:
        """
        Call Claude to generate a strategic summary of the audit findings.
        Returns a dict with keys: strengths, weaknesses, opportunities,
        estimated_value, executive_summary.
        """
        import anthropic

        score_summary = (
            f"SEO: {audit_report.seo_score:.0f}/100, "
            f"Accessibility: {audit_report.accessibility_score:.0f}/100, "
            f"Performance: {audit_report.speed_score:.0f}/100, "
            f"Security: {audit_report.security_score:.0f}/100, "
            f"UI/UX: {audit_report.ui_score:.0f}/100, "
            f"Content: {audit_report.content_score:.0f}/100, "
            f"Overall: {audit_report.overall_score:.0f}/100"
        )

        top_issues = []
        for issue_list in [
            audit_report.seo_issues or [],
            audit_report.accessibility_issues or [],
        ]:
            for issue in issue_list[:3]:
                top_issues.append(issue.get("message", ""))

        top_recs = [
            r.get("description", "")
            for r in (audit_report.recommendations or [])[:5]
        ]

        prompt = f"""You are a professional web design and digital marketing consultant.
Analyse the following website audit results for {business.name or "a local business"}
({business.city or "unknown city"}, {business.industry or "unknown industry"}):

Website: {audit_report.website_url}
Scores: {score_summary}

Top issues:
{chr(10).join(f"- {i}" for i in top_issues if i)}

Top recommendations:
{chr(10).join(f"- {r}" for r in top_recs if r)}

Provide a concise JSON response with:
- "executive_summary": 2-3 sentence overall assessment
- "strengths": list of 2-3 notable positives
- "weaknesses": list of 2-3 most critical issues
- "opportunities": list of 2-3 highest-impact improvements
- "estimated_value": your estimate of value improvement from fixing the top issues (text)

Return ONLY valid JSON with these exact keys."""

        client = anthropic.AsyncAnthropic(api_key=self.config.anthropic_api_key)
        message = await client.messages.create(
            model=self.config.ai_model,
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        import re as _re

        raw = _re.sub(r"^```(?:json)?\s*", "", raw)
        raw = _re.sub(r"\s*```$", "", raw)

        import json as _json
        try:
            return _json.loads(raw)
        except _json.JSONDecodeError:
            # Return raw text in a structured dict on parse failure
            return {
                "executive_summary": raw[:500],
                "strengths": [],
                "weaknesses": [],
                "opportunities": [],
                "estimated_value": "",
            }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mark_no_website(report: AuditReport) -> None:
    """Zero out scores when no website is reachable."""
    for attr in [
        "seo_score", "accessibility_score", "speed_score", "security_score",
        "ui_score", "ux_score", "mobile_score", "branding_score",
        "content_score", "conversion_score", "overall_score",
    ]:
        setattr(report, attr, 0.0)
    report.status = AuditStatus.completed
    report.completed_at = datetime.now(timezone.utc)


def _sync_website_status(
    business: Business, ws: WebsiteStatusResult
) -> None:
    """Propagate WebsiteStatusResult fields back onto the Business model."""
    _STATUS_MAP = {
        "active": WebsiteStatus.active,
        "inactive": WebsiteStatus.inactive,
        "parked": WebsiteStatus.parked,
        "abandoned": WebsiteStatus.abandoned,
        "missing": WebsiteStatus.missing,
    }
    status_val = _STATUS_MAP.get(ws.status, WebsiteStatus.missing)
    business.website_status = status_val
    business.has_website = ws.status == "active"
    if ws.final_url:
        business.website_url = ws.final_url
