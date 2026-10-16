"""
PerformanceAnalyzer — measure real performance metrics by driving a Playwright
page and extracting browser Navigation Timing, Resource Timing, and paint
entries via JavaScript evaluation.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class PerformanceReport:
    score: float
    metrics: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "metrics": self.metrics,
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# JavaScript snippets executed inside the page
# ---------------------------------------------------------------------------

_JS_NAVIGATION_TIMING = """
() => {
    const t = performance.getEntriesByType('navigation')[0];
    if (!t) return null;
    return {
        ttfb: t.responseStart - t.requestStart,
        dns: t.domainLookupEnd - t.domainLookupStart,
        tcp: t.connectEnd - t.connectStart,
        ssl: t.secureConnectionStart > 0 ? t.connectEnd - t.secureConnectionStart : 0,
        dom_interactive: t.domInteractive - t.startTime,
        dom_complete: t.domComplete - t.startTime,
        load_event: t.loadEventEnd - t.startTime,
        transfer_size: t.transferSize || 0,
        encoded_body_size: t.encodedBodySize || 0,
        decoded_body_size: t.decodedBodySize || 0,
    };
}
"""

_JS_PAINT_TIMING = """
() => {
    const entries = performance.getEntriesByType('paint');
    const result = {};
    for (const e of entries) {
        if (e.name === 'first-paint') result.fp = e.startTime;
        if (e.name === 'first-contentful-paint') result.fcp = e.startTime;
    }
    return result;
}
"""

_JS_RESOURCE_TIMING = """
() => {
    const resources = performance.getEntriesByType('resource');
    let totalSize = 0, jsSize = 0, cssSize = 0, imgSize = 0;
    let jsCount = 0, cssCount = 0, imgCount = 0, thirdParty = 0;
    const origin = location.origin;
    for (const r of resources) {
        const size = r.transferSize || r.encodedBodySize || 0;
        totalSize += size;
        const url = r.name;
        if (!url.startsWith(origin)) thirdParty++;
        if (/\\.js(\\?.*)?$/.test(url)) { jsSize += size; jsCount++; }
        else if (/\\.css(\\?.*)?$/.test(url)) { cssSize += size; cssCount++; }
        else if (/\\.(png|jpe?g|gif|webp|avif|svg|ico)(\\?.*)?$/i.test(url)) {
            imgSize += size; imgCount++;
        }
    }
    return {
        total_requests: resources.length,
        total_size_bytes: totalSize,
        js_size_bytes: jsSize,
        js_count: jsCount,
        css_size_bytes: cssSize,
        css_count: cssCount,
        img_size_bytes: imgSize,
        img_count: imgCount,
        third_party_count: thirdParty,
    };
}
"""

_JS_LCP = """
() => new Promise(resolve => {
    let lcp = 0;
    const obs = new PerformanceObserver(list => {
        const entries = list.getEntries();
        if (entries.length) lcp = entries[entries.length - 1].startTime;
    });
    try {
        obs.observe({type: 'largest-contentful-paint', buffered: true});
    } catch(e) { resolve(null); return; }
    setTimeout(() => { obs.disconnect(); resolve(lcp || null); }, 1500);
})
"""

_JS_CLS = """
() => new Promise(resolve => {
    let cls = 0;
    const obs = new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
            if (!entry.hadRecentInput) cls += entry.value;
        }
    });
    try {
        obs.observe({type: 'layout-shift', buffered: true});
    } catch(e) { resolve(null); return; }
    setTimeout(() => { obs.disconnect(); resolve(cls); }, 1500);
})
"""

_JS_IMAGE_AUDIT = """
() => {
    const imgs = Array.from(document.querySelectorAll('img'));
    let unoptimised = 0, noWidth = 0, noHeight = 0;
    for (const img of imgs) {
        const src = img.src || '';
        if (src && !/\\.webp|\\.avif/i.test(src)) unoptimised++;
        if (!img.width && !img.getAttribute('width')) noWidth++;
        if (!img.height && !img.getAttribute('height')) noHeight++;
    }
    return {
        total: imgs.length,
        non_modern_format: unoptimised,
        missing_dimensions: noWidth,
    };
}
"""


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class PerformanceAnalyzer:
    """
    Measure page performance by running JavaScript inside an open Playwright
    page object.

    Parameters
    ----------
    page:
        An already-navigated Playwright ``Page`` instance.  When ``None``,
        the analyser will launch its own browser (heavier; use only if no
        shared browser context is available).
    timeout_ms:
        Additional JS evaluation timeout in milliseconds.
    """

    def __init__(self, timeout_ms: int = 30_000, headless: bool = True) -> None:
        self._timeout_ms = timeout_ms
        self._headless = headless

    async def analyze(
        self,
        url: str,
        page: Optional[Any] = None,  # playwright Page or None
    ) -> PerformanceReport:
        """
        Run performance analysis on *url*.

        If *page* is supplied and already navigated to *url*, metrics are
        extracted from that page context.  Otherwise a new browser is launched.
        """
        if page is not None:
            return await self._extract_metrics(page, url)
        return await self._with_own_browser(url)

    # ------------------------------------------------------------------
    # Internal: extract metrics from page
    # ------------------------------------------------------------------

    async def _extract_metrics(self, page: Any, url: str) -> PerformanceReport:
        metrics: Dict[str, Any] = {}
        metadata: Dict[str, Any] = {"url": url}

        # Navigation timing
        try:
            nav = await page.evaluate(_JS_NAVIGATION_TIMING)
            if nav:
                metrics.update(nav)
        except Exception as exc:
            logger.debug("Navigation timing JS error: %s", exc)

        # Paint timing
        try:
            paint = await page.evaluate(_JS_PAINT_TIMING)
            if paint:
                metrics.update(paint)
        except Exception as exc:
            logger.debug("Paint timing JS error: %s", exc)

        # Resource timing
        try:
            resources = await page.evaluate(_JS_RESOURCE_TIMING)
            if resources:
                metadata.update(resources)
                metrics["page_size_bytes"] = resources.get("total_size_bytes", 0)
                metrics["total_requests"] = resources.get("total_requests", 0)
                metrics["js_size_bytes"] = resources.get("js_size_bytes", 0)
                metrics["css_size_bytes"] = resources.get("css_size_bytes", 0)
                metrics["third_party_scripts"] = resources.get("third_party_count", 0)
        except Exception as exc:
            logger.debug("Resource timing JS error: %s", exc)

        # LCP (async, needs a short wait)
        try:
            lcp = await page.evaluate(_JS_LCP)
            if lcp:
                metrics["lcp"] = lcp
        except Exception as exc:
            logger.debug("LCP JS error: %s", exc)

        # CLS
        try:
            cls = await page.evaluate(_JS_CLS)
            if cls is not None:
                metrics["cls"] = round(cls, 4)
        except Exception as exc:
            logger.debug("CLS JS error: %s", exc)

        # Image audit
        try:
            img_audit = await page.evaluate(_JS_IMAGE_AUDIT)
            if img_audit:
                metadata["image_audit"] = img_audit
        except Exception as exc:
            logger.debug("Image audit JS error: %s", exc)

        # Derive human-readable sizes
        metrics["page_size_kb"] = round(metrics.get("page_size_bytes", 0) / 1024, 1)
        metrics["js_size_kb"] = round(metrics.get("js_size_bytes", 0) / 1024, 1)
        metrics["css_size_kb"] = round(metrics.get("css_size_bytes", 0) / 1024, 1)

        issues = _identify_issues(metrics, metadata)
        score = _calculate_score(issues)
        recommendations = _build_recommendations(issues)

        return PerformanceReport(
            score=score,
            metrics=metrics,
            recommendations=recommendations,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal: own browser launch
    # ------------------------------------------------------------------

    async def _with_own_browser(self, url: str) -> PerformanceReport:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 900},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                try:
                    await page.goto(
                        url, wait_until="networkidle", timeout=self._timeout_ms
                    )
                except Exception:
                    await page.goto(
                        url, wait_until="domcontentloaded", timeout=self._timeout_ms
                    )
                await asyncio.sleep(2)  # let LCP / CLS observers settle
                result = await self._extract_metrics(page, url)
                await context.close()
            finally:
                await browser.close()

        return result


# ---------------------------------------------------------------------------
# Issue identification and scoring
# ---------------------------------------------------------------------------


@dataclass
class _PerfIssue:
    key: str
    severity: str  # critical | high | medium | low
    message: str
    recommendation: str


def _identify_issues(
    metrics: Dict[str, Any], metadata: Dict[str, Any]
) -> List[_PerfIssue]:
    issues: List[_PerfIssue] = []

    ttfb = metrics.get("ttfb")
    if ttfb is not None:
        if ttfb > 1800:
            issues.append(
                _PerfIssue(
                    "ttfb_critical",
                    "critical",
                    f"TTFB is very slow: {ttfb:.0f} ms (threshold: 800 ms).",
                    "Optimise server response: use a CDN, caching, and faster hosting.",
                )
            )
        elif ttfb > 800:
            issues.append(
                _PerfIssue(
                    "ttfb_high",
                    "high",
                    f"TTFB is slow: {ttfb:.0f} ms (threshold: 800 ms).",
                    "Reduce server response time with caching and CDN delivery.",
                )
            )

    fcp = metrics.get("fcp")
    if fcp is not None:
        if fcp > 3000:
            issues.append(
                _PerfIssue(
                    "fcp_slow",
                    "high",
                    f"First Contentful Paint: {fcp:.0f} ms (threshold: 1800 ms).",
                    "Eliminate render-blocking resources, defer non-critical CSS/JS.",
                )
            )

    lcp = metrics.get("lcp")
    if lcp is not None:
        if lcp > 4000:
            issues.append(
                _PerfIssue(
                    "lcp_critical",
                    "critical",
                    f"LCP is very slow: {lcp:.0f} ms (threshold: 2500 ms).",
                    "Preload the LCP image/element, optimise server response, use CDN.",
                )
            )
        elif lcp > 2500:
            issues.append(
                _PerfIssue(
                    "lcp_high",
                    "high",
                    f"LCP needs improvement: {lcp:.0f} ms (threshold: 2500 ms).",
                    "Optimise image sizes and server response for the LCP element.",
                )
            )

    cls = metrics.get("cls")
    if cls is not None:
        if cls > 0.25:
            issues.append(
                _PerfIssue(
                    "cls_critical",
                    "critical",
                    f"Cumulative Layout Shift: {cls:.3f} (threshold: 0.1).",
                    "Set explicit width/height on images; avoid injecting content above the fold.",
                )
            )
        elif cls > 0.1:
            issues.append(
                _PerfIssue(
                    "cls_high",
                    "medium",
                    f"CLS needs improvement: {cls:.3f} (threshold: 0.1).",
                    "Reserve space for dynamically loaded content.",
                )
            )

    page_size_kb = metrics.get("page_size_kb", 0)
    if page_size_kb > 5000:
        issues.append(
            _PerfIssue(
                "page_size_critical",
                "critical",
                f"Page size is {page_size_kb:.0f} KB — very large.",
                "Enable GZIP/Brotli compression; remove unused CSS/JS; optimise images.",
            )
        )
    elif page_size_kb > 2000:
        issues.append(
            _PerfIssue(
                "page_size_large",
                "high",
                f"Page size is {page_size_kb:.0f} KB.",
                "Compress resources and remove unused assets.",
            )
        )

    js_kb = metrics.get("js_size_kb", 0)
    if js_kb > 1000:
        issues.append(
            _PerfIssue(
                "js_size_large",
                "high",
                f"JavaScript bundle size is {js_kb:.0f} KB.",
                "Code-split bundles, tree-shake unused code, and defer non-critical JS.",
            )
        )

    tp = metrics.get("third_party_scripts", 0)
    if tp > 10:
        issues.append(
            _PerfIssue(
                "too_many_third_party",
                "medium",
                f"{tp} third-party scripts detected.",
                "Audit third-party scripts; remove unused ones and defer/async load the rest.",
            )
        )

    img_audit = metadata.get("image_audit", {})
    non_modern = img_audit.get("non_modern_format", 0)
    if non_modern > 3:
        issues.append(
            _PerfIssue(
                "non_modern_images",
                "medium",
                f"{non_modern} image(s) not using modern formats (WebP/AVIF).",
                "Convert images to WebP or AVIF for significant size savings.",
            )
        )

    return issues


_SEVERITY_WEIGHTS = {"critical": 20, "high": 10, "medium": 5, "low": 2}


def _calculate_score(issues: List[_PerfIssue]) -> float:
    penalty = sum(_SEVERITY_WEIGHTS.get(i.severity, 0) for i in issues)
    return max(0.0, min(100.0, 100.0 - penalty))


def _build_recommendations(issues: List[_PerfIssue]) -> List[Dict[str, Any]]:
    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4}
    recs = []
    for i in issues:
        recs.append(
            {
                "category": "performance",
                "priority": priority_map.get(i.severity, 5),
                "title": i.key.replace("_", " ").title(),
                "description": i.recommendation,
                "severity": i.severity,
            }
        )
    recs.sort(key=lambda r: r["priority"])
    return recs
