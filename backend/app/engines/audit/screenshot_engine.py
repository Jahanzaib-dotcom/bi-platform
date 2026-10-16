"""
ScreenshotEngine — capture viewport and full-page screenshots via Playwright.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class CaptureResult:
    viewport: str          # desktop | mobile | tablet | full_page
    file_path: str
    file_url: str
    width: int
    height: int
    file_size: int
    captured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Viewport definitions
# ---------------------------------------------------------------------------

_VIEWPORTS: Dict[str, Dict] = {
    "desktop": {
        "width": 1440,
        "height": 900,
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
    },
    "mobile": {
        "width": 390,
        "height": 844,
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
        "user_agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
    },
    "tablet": {
        "width": 768,
        "height": 1024,
        "device_scale_factor": 2,
        "is_mobile": True,
        "has_touch": True,
        "user_agent": (
            "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
    },
    "full_page": {
        "width": 1440,
        "height": 900,
        "device_scale_factor": 1,
        "is_mobile": False,
        "has_touch": False,
    },
}

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class ScreenshotEngine:
    """
    Capture screenshots of a web page at desktop, mobile, tablet, and
    full-page viewports using Playwright (async API).

    Parameters
    ----------
    screenshot_dir:
        Absolute path to the directory where screenshots are persisted.
    base_url:
        Optional base URL prefix used to construct ``file_url`` values
        (e.g. ``https://cdn.example.com/screenshots``).  When omitted the
        ``file_path`` is used as the URL as well.
    timeout_ms:
        Navigation timeout in milliseconds.
    headless:
        Run browser in headless mode.
    """

    def __init__(
        self,
        screenshot_dir: str | Path = "./storage/screenshots",
        base_url: str = "",
        timeout_ms: int = 30_000,
        headless: bool = True,
    ) -> None:
        self._dir = Path(screenshot_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._base_url = base_url.rstrip("/")
        self._timeout_ms = timeout_ms
        self._headless = headless

    # ------------------------------------------------------------------
    # Public capture helpers
    # ------------------------------------------------------------------

    async def capture_desktop(self, url: str) -> CaptureResult:
        return await self._capture(url, "desktop", full_page=False)

    async def capture_mobile(self, url: str) -> CaptureResult:
        return await self._capture(url, "mobile", full_page=False)

    async def capture_tablet(self, url: str) -> CaptureResult:
        return await self._capture(url, "tablet", full_page=False)

    async def capture_full_page(self, url: str) -> CaptureResult:
        return await self._capture(url, "full_page", full_page=True)

    async def capture_all(self, url: str) -> Dict[str, CaptureResult]:
        """
        Capture all four viewports concurrently and return a mapping of
        ``viewport_name -> CaptureResult``.
        """
        tasks = {
            "desktop": self.capture_desktop(url),
            "mobile": self.capture_mobile(url),
            "tablet": self.capture_tablet(url),
            "full_page": self.capture_full_page(url),
        }
        results: Dict[str, CaptureResult] = {}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for name, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.error("Screenshot failed for %s/%s: %s", url, name, result)
                results[name] = CaptureResult(
                    viewport=name,
                    file_path="",
                    file_url="",
                    width=0,
                    height=0,
                    file_size=0,
                    error=str(result),
                )
            else:
                results[name] = result
        return results

    # ------------------------------------------------------------------
    # Internal implementation
    # ------------------------------------------------------------------

    async def _capture(
        self, url: str, viewport_name: str, full_page: bool
    ) -> CaptureResult:
        """
        Launch a Playwright browser context, navigate to *url*, and capture
        a screenshot for the given viewport configuration.
        """
        from playwright.async_api import async_playwright

        vp = _VIEWPORTS[viewport_name]
        file_path = self._build_path(url, viewport_name)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            try:
                context_kwargs: Dict = {
                    "viewport": {"width": vp["width"], "height": vp["height"]},
                    "device_scale_factor": vp.get("device_scale_factor", 1),
                    "is_mobile": vp.get("is_mobile", False),
                    "has_touch": vp.get("has_touch", False),
                    "user_agent": vp.get("user_agent", _DEFAULT_USER_AGENT),
                }
                context = await browser.new_context(**context_kwargs)
                page = await context.new_page()

                try:
                    await page.goto(
                        url,
                        wait_until="networkidle",
                        timeout=self._timeout_ms,
                    )
                except Exception:
                    # Fall back to domcontentloaded if networkidle times out
                    try:
                        await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=self._timeout_ms // 2,
                        )
                    except Exception as exc2:
                        raise RuntimeError(f"Navigation failed for {url}: {exc2}") from exc2

                # Give JS a moment to settle
                await asyncio.sleep(1.5)

                # Remove cookie/overlay banners heuristically
                await _dismiss_overlays(page)

                await page.screenshot(
                    path=str(file_path),
                    full_page=full_page,
                    type="png",
                )

                await context.close()
            finally:
                await browser.close()

        file_size = file_path.stat().st_size if file_path.exists() else 0
        file_url = self._build_url(file_path)

        return CaptureResult(
            viewport=viewport_name,
            file_path=str(file_path),
            file_url=file_url,
            width=vp["width"],
            height=vp["height"],
            file_size=file_size,
        )

    # ------------------------------------------------------------------
    # Path / URL helpers
    # ------------------------------------------------------------------

    def _build_path(self, url: str, viewport: str) -> Path:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"{url_hash}_{viewport}_{ts}.png"
        return self._dir / filename

    def _build_url(self, path: Path) -> str:
        if self._base_url:
            return f"{self._base_url}/{path.name}"
        return str(path)


# ---------------------------------------------------------------------------
# Helper: dismiss common cookie banners / overlays
# ---------------------------------------------------------------------------


async def _dismiss_overlays(page) -> None:  # noqa: ANN001
    """
    Best-effort removal of cookie consent banners and other overlays that
    might obscure content in screenshots.
    """
    selectors = [
        "[id*='cookie'] button",
        "[class*='cookie'] button",
        "[id*='consent'] button",
        "[class*='consent'] button",
        "[class*='gdpr'] button",
        "[id*='gdpr'] button",
        "button[aria-label*='Accept']",
        "button[aria-label*='agree']",
        "#onetrust-accept-btn-handler",
        ".cc-accept",
        ".cc-allow",
        "[data-cookiebanner] button",
    ]
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if el:
                await el.click(timeout=2000)
                break
        except Exception:
            continue
