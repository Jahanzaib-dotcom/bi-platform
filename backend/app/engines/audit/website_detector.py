"""
WebsiteDetector — probe a URL (or discover one for a business) and return
a structured WebsiteStatus result.
"""
from __future__ import annotations

import asyncio
import re
import ssl
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import tldextract

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class WebsiteStatusResult:
    """Full result returned by WebsiteDetector.detect()."""

    status: str  # active | inactive | parked | abandoned | missing | error
    final_url: str
    original_url: str
    redirect_chain: List[str] = field(default_factory=list)
    ssl_valid: bool = False
    ssl_expires: Optional[datetime] = None
    status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    is_parked: bool = False
    is_redirect: bool = False
    error: Optional[str] = None
    page_title: Optional[str] = None


# ---------------------------------------------------------------------------
# Parking-page heuristics
# ---------------------------------------------------------------------------

_PARKING_TITLE_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"domain (is )?for sale",
        r"this domain",
        r"buy this domain",
        r"parked (free )?by",
        r"sedoparking",
        r"godaddy\.com",
        r"domain parking",
        r"under construction",
        r"coming soon",
        r"website coming soon",
        r"page not found",
    ]
]

_PARKING_BODY_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"domain (is )?for sale",
        r"parked (free )?by",
        r"sedoparking\.com",
        r"hugedomains\.com",
        r"dan\.com",
        r"afternic\.com",
        r"sedo\.com",
        r"domainmarket\.com",
        r"register\.com",
        r"namecheap parking",
        r"this web page is parked",
        r"inquire about this domain",
        r"make an offer",
    ]
]

_PARKING_HOST_PATTERNS: List[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"sedoparking\.com",
        r"parkingcrew\.net",
        r"bodis\.com",
        r"above\.com",
    ]
]


def _is_parked_content(title: str, body: str, final_url: str) -> bool:
    for pat in _PARKING_TITLE_PATTERNS:
        if pat.search(title):
            return True
    for pat in _PARKING_BODY_PATTERNS:
        if pat.search(body):
            return True
    for pat in _PARKING_HOST_PATTERNS:
        if pat.search(final_url):
            return True
    return False


# ---------------------------------------------------------------------------
# SSL helper (synchronous, run in thread)
# ---------------------------------------------------------------------------


def _get_ssl_info(hostname: str) -> tuple[bool, Optional[datetime]]:
    """Return (valid, expiry_datetime) for the given hostname."""
    context = ssl.create_default_context()
    try:
        conn = context.wrap_socket(
            __import__("socket").create_connection((hostname, 443), timeout=10),
            server_hostname=hostname,
        )
        cert = conn.getpeercert()
        conn.close()
        not_after_str = cert.get("notAfter", "")
        if not_after_str:
            expiry = datetime.strptime(not_after_str, "%b %d %H:%M:%S %Y %Z").replace(
                tzinfo=timezone.utc
            )
            valid = expiry > datetime.now(timezone.utc)
            return valid, expiry
        return True, None
    except Exception:
        return False, None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class WebsiteDetector:
    """
    Probes a URL and returns a WebsiteStatusResult describing the live state
    of the site. Also provides a best-effort website discovery path via
    DuckDuckGo scraping for businesses that have no known URL.
    """

    def __init__(
        self,
        timeout: float = 15.0,
        max_redirects: int = 10,
        user_agent: str = (
            "Mozilla/5.0 (compatible; BIAuditBot/1.0; +https://bi-platform.io/bot)"
        ),
    ) -> None:
        self._timeout = timeout
        self._max_redirects = max_redirects
        self._user_agent = user_agent

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def detect(self, url: str) -> WebsiteStatusResult:
        """
        Probe *url* and return a full WebsiteStatusResult.

        Steps
        -----
        1. Normalise URL.
        2. Follow redirect chain (manual, so we capture the chain).
        3. On success, fetch the page body to look for parking indicators.
        4. Probe SSL.
        """
        url = _normalise_url(url)
        result = WebsiteStatusResult(
            status="missing",
            final_url=url,
            original_url=url,
        )

        headers = {
            "User-Agent": self._user_agent,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            # --- manual redirect chain tracking ---
            redirect_chain: List[str] = [url]
            current_url = url
            status_code: Optional[int] = None
            response_text = ""
            page_title = ""
            start = asyncio.get_event_loop().time()

            async with httpx.AsyncClient(
                follow_redirects=True,
                max_redirects=self._max_redirects,
                timeout=self._timeout,
                headers=headers,
                verify=False,  # we check SSL manually
            ) as client:
                response = await client.get(current_url)
                status_code = response.status_code
                elapsed_ms = (asyncio.get_event_loop().time() - start) * 1000
                result.response_time_ms = round(elapsed_ms, 1)

                # Capture redirect chain from httpx history
                if response.history:
                    for r in response.history:
                        redirect_chain.append(str(r.url))
                redirect_chain.append(str(response.url))
                # Deduplicate while preserving order
                seen: set = set()
                clean_chain: List[str] = []
                for u in redirect_chain:
                    if u not in seen:
                        seen.add(u)
                        clean_chain.append(u)

                result.redirect_chain = clean_chain
                result.final_url = str(response.url)
                result.is_redirect = len(response.history) > 0
                result.status_code = status_code

                if status_code in (200, 206):
                    response_text = response.text[:50_000]  # cap at 50 kB
                    page_title = _extract_title(response_text)
                    result.page_title = page_title

                    if _is_parked_content(page_title, response_text, result.final_url):
                        result.status = "parked"
                        result.is_parked = True
                    elif _looks_abandoned(response_text):
                        result.status = "abandoned"
                    else:
                        result.status = "active"

                elif status_code in (301, 302, 303, 307, 308):
                    # httpx already followed; if we land here status is final
                    result.status = "active"
                elif status_code in (404, 410):
                    result.status = "inactive"
                elif status_code >= 500:
                    result.status = "inactive"
                else:
                    result.status = "inactive"

        except httpx.ConnectError as exc:
            result.status = "missing"
            result.error = f"Connection error: {exc}"
        except httpx.TimeoutException as exc:
            result.status = "inactive"
            result.error = f"Timeout: {exc}"
        except Exception as exc:
            result.status = "error"
            result.error = str(exc)

        # --- SSL probe (only meaningful for https) ---
        parsed = urllib.parse.urlparse(result.final_url)
        if parsed.scheme == "https" and parsed.hostname:
            try:
                ssl_valid, ssl_expires = await asyncio.get_event_loop().run_in_executor(
                    None, _get_ssl_info, parsed.hostname
                )
                result.ssl_valid = ssl_valid
                result.ssl_expires = ssl_expires
            except Exception:
                result.ssl_valid = False

        return result

    async def discover_website(
        self, business_name: str, city: str
    ) -> Optional[str]:
        """
        Attempt to find the official website for a business by scraping
        DuckDuckGo HTML search results.  Returns the first plausible URL
        that is not a social/directory site, or None.
        """
        query = urllib.parse.quote_plus(f"{business_name} {city} official website")
        search_url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {
            "User-Agent": self._user_agent,
            "Accept-Language": "en-US,en;q=0.9",
        }

        _SKIP_DOMAINS = {
            "facebook.com",
            "twitter.com",
            "instagram.com",
            "linkedin.com",
            "yelp.com",
            "yellowpages.com",
            "bbb.org",
            "google.com",
            "bing.com",
            "duckduckgo.com",
            "wikipedia.org",
            "tripadvisor.com",
            "foursquare.com",
            "angieslist.com",
            "homeadvisor.com",
            "thumbtack.com",
            "manta.com",
            "chamberofcommerce.com",
        }

        try:
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=15.0, headers=headers
            ) as client:
                resp = await client.get(search_url)
                if resp.status_code != 200:
                    return None
                html = resp.text

            # Parse anchors from DDG result HTML
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a.result__url, a.result__a"):
                href = a.get("href", "")
                if not href:
                    continue
                # DDG wraps URLs in redirects sometimes
                if "duckduckgo.com/l/?uddg=" in href:
                    inner = urllib.parse.parse_qs(
                        urllib.parse.urlparse(href).query
                    ).get("uddg", [None])[0]
                    if inner:
                        href = urllib.parse.unquote(inner)
                if not href.startswith("http"):
                    continue
                ext = tldextract.extract(href)
                domain = f"{ext.domain}.{ext.suffix}".lower()
                if any(skip in domain for skip in _SKIP_DOMAINS):
                    continue
                return href.split("?")[0].rstrip("/")
        except Exception:
            pass

        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalise_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if match:
        return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def _looks_abandoned(html: str) -> bool:
    """
    Very light heuristic: if the page has very little content it is likely
    abandoned or a placeholder.
    """
    # Strip tags and measure text length
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return len(text) < 200
