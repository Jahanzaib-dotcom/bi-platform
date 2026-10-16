"""
ScraperEngine — Playwright-based async web scraper.

Responsibilities
----------------
* Full page scrape: title, meta tags, headings, links, images, text, forms,
  schema.org JSON-LD, raw HTML source.
* Technology-stack fingerprinting (delegates to TechStackDetector).
* Lightweight metadata probe (HEAD + minimal GET).
* robots.txt / sitemap.xml fetching.
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import settings
from app.core.logging import get_logger
from app.engines.scraper.tech_detector import TechDetectionResult, TechStackDetector

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ScrapedLink:
    href: str
    text: str
    rel: Optional[str] = None
    is_external: bool = False


@dataclass
class ScrapedImage:
    src: str
    alt: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


@dataclass
class ScrapedForm:
    action: Optional[str]
    method: str
    fields: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ScrapedData:
    """Full scraped payload for a single URL."""

    # Provenance
    url: str
    final_url: str
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Page fundamentals
    title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    meta_tags: Dict[str, str] = field(default_factory=dict)
    canonical_url: Optional[str] = None

    # Open Graph / Twitter card
    og_tags: Dict[str, str] = field(default_factory=dict)
    twitter_tags: Dict[str, str] = field(default_factory=dict)

    # Content
    headings: Dict[str, List[str]] = field(default_factory=dict)
    links: List[ScrapedLink] = field(default_factory=list)
    images: List[ScrapedImage] = field(default_factory=list)
    forms: List[ScrapedForm] = field(default_factory=list)
    text_content: Optional[str] = None
    word_count: int = 0

    # Structured data
    json_ld: List[Dict[str, Any]] = field(default_factory=list)

    # Technology
    tech_stack: Optional[TechDetectionResult] = None

    # Raw source
    html_source: Optional[str] = None

    # HTTP metadata
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    content_type: Optional[str] = None
    page_size_bytes: int = 0

    # Error
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "scraped_at": self.scraped_at.isoformat(),
            "title": self.title,
            "meta_description": self.meta_description,
            "meta_keywords": self.meta_keywords,
            "meta_tags": self.meta_tags,
            "canonical_url": self.canonical_url,
            "og_tags": self.og_tags,
            "twitter_tags": self.twitter_tags,
            "headings": self.headings,
            "links": [
                {
                    "href": lnk.href,
                    "text": lnk.text,
                    "rel": lnk.rel,
                    "is_external": lnk.is_external,
                }
                for lnk in self.links
            ],
            "images": [
                {
                    "src": img.src,
                    "alt": img.alt,
                    "width": img.width,
                    "height": img.height,
                }
                for img in self.images
            ],
            "forms": [
                {
                    "action": frm.action,
                    "method": frm.method,
                    "fields": frm.fields,
                }
                for frm in self.forms
            ],
            "text_content": self.text_content,
            "word_count": self.word_count,
            "json_ld": self.json_ld,
            "tech_stack": self.tech_stack.to_dict() if self.tech_stack else None,
            "html_source": self.html_source,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "content_type": self.content_type,
            "page_size_bytes": self.page_size_bytes,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# ScraperConfig
# ---------------------------------------------------------------------------


@dataclass
class ScraperConfig:
    """Tunable parameters for a single scrape run."""

    timeout_ms: int = 30_000
    headless: bool = True
    capture_html: bool = True
    # Maximum HTML stored in result (bytes).  0 = unlimited.
    max_html_bytes: int = 500_000
    # Whether to execute JS (True = full Playwright; False = httpx-only).
    javascript: bool = True
    user_agent: str = (
        "Mozilla/5.0 (compatible; BIScraperBot/1.0; +https://bi-platform.io/bot)"
    )
    # Extra headers forwarded to the browser / httpx client.
    extra_headers: Dict[str, str] = field(default_factory=dict)
    # Maximum number of links to store in the result.
    max_links: int = 500


# ---------------------------------------------------------------------------
# ScraperEngine
# ---------------------------------------------------------------------------


class ScraperEngine:
    """
    Playwright-based async scraper.

    The engine lazily starts Playwright on first use and shuts it down when
    used as an async context manager::

        async with ScraperEngine() as engine:
            data = await engine.scrape_website(url)
    """

    _DEFAULT_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
    }

    def __init__(self) -> None:
        self._tech_detector = TechStackDetector()
        self._playwright = None
        self._browser = None

    # ------------------------------------------------------------------
    # Context manager helpers
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "ScraperEngine":
        await self._ensure_browser()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self._close_browser()

    async def _ensure_browser(self) -> None:
        """Start Playwright browser if not already running."""
        if self._browser is not None:
            return
        try:
            from playwright.async_api import async_playwright  # type: ignore

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=settings.PLAYWRIGHT_HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            logger.debug("playwright.browser.started")
        except Exception as exc:
            logger.warning("playwright.browser.start_failed", error=str(exc))
            self._browser = None

    async def _close_browser(self) -> None:
        """Gracefully close the Playwright browser."""
        try:
            if self._browser:
                await self._browser.close()
                self._browser = None
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
            logger.debug("playwright.browser.closed")
        except Exception as exc:
            logger.warning("playwright.browser.close_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scrape_website(
        self,
        url: str,
        config: Optional[ScraperConfig] = None,
    ) -> ScrapedData:
        """
        Fully scrape *url* using Playwright (JavaScript executed).

        Falls back to a plain httpx GET if Playwright is unavailable.

        Returns
        -------
        ScrapedData
        """
        config = config or ScraperConfig()
        url = _normalise_url(url)
        result = ScrapedData(url=url, final_url=url)

        await self._ensure_browser()

        if self._browser and config.javascript:
            await self._scrape_with_playwright(url, config, result)
        else:
            await self._scrape_with_httpx(url, config, result)

        return result

    async def get_page_metadata(self, url: str) -> Dict[str, Any]:
        """
        Fast HEAD + minimal GET for quick metadata checks.

        Returns a dict with status_code, content_type, content_length,
        response_time_ms, final_url, and server header if present.
        """
        url = _normalise_url(url)
        meta: Dict[str, Any] = {
            "url": url,
            "final_url": url,
            "status_code": None,
            "content_type": None,
            "content_length": None,
            "response_time_ms": None,
            "server": None,
            "x_powered_by": None,
            "redirect_chain": [],
            "error": None,
        }

        headers = {**self._DEFAULT_HEADERS}
        start = asyncio.get_event_loop().time()

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=15.0,
                headers=headers,
                verify=False,
            ) as client:
                # Try HEAD first (faster, no body)
                try:
                    head_resp = await client.head(url)
                    elapsed = (asyncio.get_event_loop().time() - start) * 1000
                    meta["status_code"] = head_resp.status_code
                    meta["response_time_ms"] = round(elapsed, 1)
                    meta["final_url"] = str(head_resp.url)
                    meta["content_type"] = head_resp.headers.get("content-type")
                    meta["content_length"] = head_resp.headers.get("content-length")
                    meta["server"] = head_resp.headers.get("server")
                    meta["x_powered_by"] = head_resp.headers.get("x-powered-by")
                    meta["redirect_chain"] = [
                        str(r.url) for r in head_resp.history
                    ] + [str(head_resp.url)]
                    # If HEAD returns 405 fall through to GET
                    if head_resp.status_code == 405:
                        raise httpx.HTTPStatusError(
                            "HEAD not allowed", request=head_resp.request, response=head_resp
                        )
                except httpx.HTTPStatusError:
                    # Fall back to GET with stream (read only headers)
                    start = asyncio.get_event_loop().time()
                    async with client.stream("GET", url) as resp:
                        elapsed = (asyncio.get_event_loop().time() - start) * 1000
                        meta["status_code"] = resp.status_code
                        meta["response_time_ms"] = round(elapsed, 1)
                        meta["final_url"] = str(resp.url)
                        meta["content_type"] = resp.headers.get("content-type")
                        meta["content_length"] = resp.headers.get("content-length")
                        meta["server"] = resp.headers.get("server")
                        meta["x_powered_by"] = resp.headers.get("x-powered-by")
                        meta["redirect_chain"] = [
                            str(r.url) for r in resp.history
                        ] + [str(resp.url)]
        except Exception as exc:
            meta["error"] = str(exc)

        return meta

    async def check_robots_sitemap(self, base_url: str) -> Dict[str, Any]:
        """
        Fetch and parse robots.txt and sitemap.xml for *base_url*.

        Returns
        -------
        dict with keys:
          robots_txt      – raw text of robots.txt (None if unavailable)
          robots_rules    – parsed {user_agent: {allow, disallow}} mapping
          sitemap_urls    – list of sitemap URLs from robots.txt / sitemap.xml
          sitemap_entries – list of URLs found in sitemap.xml (up to 1000)
          crawl_delay     – crawl-delay value if present
        """
        base_url = _normalise_url(base_url).rstrip("/")
        parsed = urllib.parse.urlparse(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        result: Dict[str, Any] = {
            "robots_txt": None,
            "robots_rules": {},
            "sitemap_urls": [],
            "sitemap_entries": [],
            "crawl_delay": None,
        }

        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            verify=False,
            headers=self._DEFAULT_HEADERS,
        ) as client:
            # -- robots.txt --
            robots_url = f"{origin}/robots.txt"
            try:
                resp = await client.get(robots_url)
                if resp.status_code == 200 and "text" in resp.headers.get(
                    "content-type", "text"
                ):
                    robots_text = resp.text
                    result["robots_txt"] = robots_text
                    result["robots_rules"], result["crawl_delay"], sitemap_lines = (
                        _parse_robots(robots_text)
                    )
                    result["sitemap_urls"].extend(sitemap_lines)
            except Exception as exc:
                logger.debug("robots_txt.fetch_failed", url=robots_url, error=str(exc))

            # -- sitemap.xml (if not already found via robots) --
            if not result["sitemap_urls"]:
                result["sitemap_urls"].append(f"{origin}/sitemap.xml")

            # -- Fetch first sitemap and extract URLs --
            for sm_url in result["sitemap_urls"][:3]:  # cap at 3 sitemaps
                try:
                    sm_resp = await client.get(sm_url)
                    if sm_resp.status_code == 200:
                        entries = _parse_sitemap(sm_resp.text)
                        result["sitemap_entries"].extend(entries)
                        if len(result["sitemap_entries"]) >= 1000:
                            result["sitemap_entries"] = result["sitemap_entries"][:1000]
                            break
                except Exception as exc:
                    logger.debug("sitemap.fetch_failed", url=sm_url, error=str(exc))

        return result

    # ------------------------------------------------------------------
    # Private: Playwright scraper
    # ------------------------------------------------------------------

    async def _scrape_with_playwright(
        self,
        url: str,
        config: ScraperConfig,
        result: ScrapedData,
    ) -> None:
        """Scrape *url* using a full Playwright page load."""
        from playwright.async_api import Error as PlaywrightError  # type: ignore
        from playwright.async_api import Page  # type: ignore

        page: Optional[Page] = None
        try:
            context = await self._browser.new_context(
                user_agent=config.user_agent,
                extra_http_headers=config.extra_headers,
                ignore_https_errors=True,
                viewport={"width": 1280, "height": 900},
            )
            page = await context.new_page()

            # Intercept responses to capture status / response time
            response_info: Dict[str, Any] = {}
            start_time = asyncio.get_event_loop().time()

            async def on_response(response: Any) -> None:
                if str(response.url) == url or (
                    not response_info and response.status < 400
                ):
                    response_info["status"] = response.status
                    response_info["headers"] = dict(response.headers)
                    response_info["url"] = str(response.url)

            page.on("response", on_response)

            await page.goto(url, timeout=config.timeout_ms, wait_until="domcontentloaded")
            # Give JS a moment to render dynamic content
            await page.wait_for_timeout(1500)

            elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            result.response_time_ms = round(elapsed_ms, 1)
            result.final_url = page.url
            result.status_code = response_info.get("status", 200)
            result.content_type = response_info.get("headers", {}).get("content-type")

            html = await page.content()
            result.page_size_bytes = len(html.encode("utf-8"))

            if config.capture_html:
                if config.max_html_bytes and len(html) > config.max_html_bytes:
                    result.html_source = html[: config.max_html_bytes]
                else:
                    result.html_source = html

            # Parse the rendered HTML
            await asyncio.get_event_loop().run_in_executor(
                None, self._parse_html, html, result, url, config
            )

            # Tech detection on rendered HTML + response headers
            resp_headers = response_info.get("headers", {})
            result.tech_stack = self._tech_detector.detect(
                html=html, headers=resp_headers
            )

            logger.info(
                "scraper.playwright.success",
                url=url,
                final_url=result.final_url,
                status=result.status_code,
                elapsed_ms=result.response_time_ms,
            )

        except PlaywrightError as exc:
            result.error = f"Playwright error: {exc}"
            logger.warning("scraper.playwright.error", url=url, error=str(exc))
            # Fall back to httpx
            await self._scrape_with_httpx(url, config, result)
        except Exception as exc:
            result.error = str(exc)
            logger.warning("scraper.playwright.unexpected_error", url=url, error=str(exc))
        finally:
            if page:
                try:
                    await page.context.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Private: httpx fallback scraper
    # ------------------------------------------------------------------

    async def _scrape_with_httpx(
        self,
        url: str,
        config: ScraperConfig,
        result: ScrapedData,
    ) -> None:
        """Scrape *url* using plain httpx (no JavaScript execution)."""
        headers = {
            **self._DEFAULT_HEADERS,
            "User-Agent": config.user_agent,
            **config.extra_headers,
        }

        start = asyncio.get_event_loop().time()
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=config.timeout_ms / 1000,
                headers=headers,
                verify=False,
            ) as client:
                resp = await client.get(url)
                elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000

                result.status_code = resp.status_code
                result.final_url = str(resp.url)
                result.response_time_ms = round(elapsed_ms, 1)
                result.content_type = resp.headers.get("content-type")

                html = resp.text
                result.page_size_bytes = len(resp.content)

                if config.capture_html:
                    if config.max_html_bytes and len(html) > config.max_html_bytes:
                        result.html_source = html[: config.max_html_bytes]
                    else:
                        result.html_source = html

                self._parse_html(html, result, url, config)

                resp_headers = dict(resp.headers)
                result.tech_stack = self._tech_detector.detect(
                    html=html, headers=resp_headers
                )

                logger.info(
                    "scraper.httpx.success",
                    url=url,
                    final_url=result.final_url,
                    status=result.status_code,
                    elapsed_ms=result.response_time_ms,
                )

        except Exception as exc:
            result.error = str(exc)
            logger.warning("scraper.httpx.error", url=url, error=str(exc))

    # ------------------------------------------------------------------
    # Private: HTML parser
    # ------------------------------------------------------------------

    def _parse_html(
        self,
        html: str,
        result: ScrapedData,
        base_url: str,
        config: ScraperConfig,
    ) -> None:
        """
        Parse *html* with BeautifulSoup and populate *result* in-place.
        Runs synchronously (safe to call in an executor).
        """
        soup = BeautifulSoup(html, "lxml")

        # ---- Title ----
        title_tag = soup.find("title")
        result.title = title_tag.get_text(strip=True) if title_tag else None

        # ---- Meta tags ----
        for tag in soup.find_all("meta"):
            if not isinstance(tag, Tag):
                continue
            name = (
                tag.get("name") or tag.get("property") or tag.get("http-equiv") or ""
            )
            content = tag.get("content", "")
            if not name or not content:
                continue
            name = str(name).lower()
            result.meta_tags[name] = str(content)
            if name == "description":
                result.meta_description = str(content)
            elif name == "keywords":
                result.meta_keywords = str(content)

        # ---- Canonical ----
        canonical = soup.find("link", rel="canonical")
        if canonical and isinstance(canonical, Tag):
            result.canonical_url = canonical.get("href")

        # ---- Open Graph ----
        for tag in soup.find_all("meta", property=re.compile(r"^og:", re.I)):
            if isinstance(tag, Tag):
                prop = str(tag.get("property", "")).replace("og:", "").lower()
                result.og_tags[prop] = str(tag.get("content", ""))

        # ---- Twitter Card ----
        for tag in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:", re.I)}):
            if isinstance(tag, Tag):
                tw_name = str(tag.get("name", "")).replace("twitter:", "").lower()
                result.twitter_tags[tw_name] = str(tag.get("content", ""))

        # ---- Headings ----
        for level in ("h1", "h2", "h3", "h4", "h5", "h6"):
            texts = [
                h.get_text(strip=True)
                for h in soup.find_all(level)
                if h.get_text(strip=True)
            ]
            if texts:
                result.headings[level] = texts

        # ---- Links ----
        parsed_base = urllib.parse.urlparse(base_url)
        base_netloc = parsed_base.netloc.lower()
        links_seen: set[str] = set()

        for a_tag in soup.find_all("a", href=True):
            if not isinstance(a_tag, Tag):
                continue
            href = str(a_tag["href"]).strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_href = urllib.parse.urljoin(base_url, href)
            if abs_href in links_seen:
                continue
            links_seen.add(abs_href)
            parsed_href = urllib.parse.urlparse(abs_href)
            is_external = parsed_href.netloc.lower() != base_netloc
            rel_attr = a_tag.get("rel")
            rel_str = " ".join(rel_attr) if isinstance(rel_attr, list) else rel_attr
            result.links.append(
                ScrapedLink(
                    href=abs_href,
                    text=a_tag.get_text(strip=True)[:200],
                    rel=rel_str,
                    is_external=is_external,
                )
            )
            if len(result.links) >= config.max_links:
                break

        # ---- Images ----
        for img_tag in soup.find_all("img"):
            if not isinstance(img_tag, Tag):
                continue
            src = img_tag.get("src") or img_tag.get("data-src") or img_tag.get("data-lazy-src")
            if not src:
                continue
            abs_src = urllib.parse.urljoin(base_url, str(src))
            width = _safe_int(img_tag.get("width"))
            height = _safe_int(img_tag.get("height"))
            result.images.append(
                ScrapedImage(
                    src=abs_src,
                    alt=img_tag.get("alt"),
                    width=width,
                    height=height,
                )
            )

        # ---- Forms ----
        for form_tag in soup.find_all("form"):
            if not isinstance(form_tag, Tag):
                continue
            action = form_tag.get("action")
            method = str(form_tag.get("method", "get")).upper()
            fields: List[Dict[str, Any]] = []
            for inp in form_tag.find_all(["input", "textarea", "select"]):
                if not isinstance(inp, Tag):
                    continue
                field_info: Dict[str, Any] = {
                    "tag": inp.name,
                    "type": inp.get("type", "text") if inp.name == "input" else inp.name,
                    "name": inp.get("name"),
                    "id": inp.get("id"),
                    "placeholder": inp.get("placeholder"),
                    "required": inp.has_attr("required"),
                }
                fields.append(field_info)
            result.forms.append(
                ScrapedForm(
                    action=str(action) if action else None,
                    method=method,
                    fields=fields,
                )
            )

        # ---- Text content ----
        # Remove script / style / nav / footer / aside noise
        for noise in soup.find_all(["script", "style", "nav", "footer", "aside", "header"]):
            noise.decompose()
        text = soup.get_text(separator=" ", strip=True)
        # Collapse whitespace
        text = re.sub(r"\s{2,}", " ", text).strip()
        result.text_content = text[:20_000]  # cap to 20 KB
        result.word_count = len(text.split())

        # ---- JSON-LD (schema.org) ----
        for script_tag in soup.find_all("script", type="application/ld+json"):
            if isinstance(script_tag, Tag):
                raw = script_tag.string or ""
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        result.json_ld.extend(parsed)
                    elif isinstance(parsed, dict):
                        result.json_ld.append(parsed)
                except json.JSONDecodeError:
                    pass


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _normalise_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_robots(text: str) -> tuple[Dict[str, Any], Optional[int], List[str]]:
    """
    Parse a robots.txt file.

    Returns
    -------
    (rules_by_agent, crawl_delay, sitemap_urls)
    """
    rules: Dict[str, Any] = {}
    current_agent: Optional[str] = None
    crawl_delay: Optional[int] = None
    sitemaps: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        directive, _, value = line.partition(":")
        directive = directive.strip().lower()
        value = value.strip()

        if directive == "user-agent":
            current_agent = value
            if current_agent not in rules:
                rules[current_agent] = {"allow": [], "disallow": []}
        elif directive == "disallow" and current_agent:
            if value:
                rules[current_agent]["disallow"].append(value)
        elif directive == "allow" and current_agent:
            if value:
                rules[current_agent]["allow"].append(value)
        elif directive == "crawl-delay":
            try:
                crawl_delay = int(float(value))
            except ValueError:
                pass
        elif directive == "sitemap":
            if value:
                sitemaps.append(value)

    return rules, crawl_delay, sitemaps


def _parse_sitemap(xml_text: str) -> List[str]:
    """Extract <loc> URLs from a sitemap XML document (handles sitemap indexes)."""
    urls: List[str] = []
    # Simple regex-based extraction (avoids full XML parsing overhead)
    for match in re.finditer(r"<loc>\s*(.*?)\s*</loc>", xml_text, re.S):
        url = match.group(1).strip()
        if url:
            urls.append(url)
    return urls
