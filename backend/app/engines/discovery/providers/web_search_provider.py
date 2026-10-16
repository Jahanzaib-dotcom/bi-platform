"""Generic web search fallback provider (no API key required)."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Engines to try in order of preference (url, result_selector, title_sel, link_sel, snippet_sel)
_ENGINES = [
    {
        "name": "bing",
        "url": "https://www.bing.com/search",
        "param": "q",
        "result_sel": ".b_algo",
        "title_sel": "h2 a",
        "link_sel": "h2 a",
        "link_attr": "href",
        "snippet_sel": ".b_caption p",
    },
    {
        "name": "mojeek",
        "url": "https://www.mojeek.com/search",
        "param": "q",
        "result_sel": "ul.results li",
        "title_sel": "a.ob",
        "link_sel": "a.ob",
        "link_attr": "href",
        "snippet_sel": "p.s",
    },
]


class _RateLimiter:
    def __init__(self, rpm: int) -> None:
        self._interval = 60.0 / rpm
        self._last: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class WebSearchProvider(BaseDiscoveryProvider):
    """
    Fallback provider that issues free-text searches to multiple search
    engines and extracts business names / URLs from the HTML result pages.

    No API key is required.  Results are coarser than API-based providers
    but provide useful coverage when other providers are exhausted.
    """

    _RATE_LIMIT_RPM = 15

    def __init__(self) -> None:
        self._limiter = _RateLimiter(self._RATE_LIMIT_RPM)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # BaseDiscoveryProvider interface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "web_search"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        start = time.monotonic()
        try:
            client = await self._get_client()
            resp = await client.get("https://www.bing.com", timeout=10)
            latency = int((time.monotonic() - start) * 1000)
            healthy = resp.status_code == 200
            return {
                "provider": self.provider_name,
                "healthy": healthy,
                "latency_ms": latency,
                "message": "OK" if healthy else f"HTTP {resp.status_code}",
            }
        except Exception as exc:
            latency = int((time.monotonic() - start) * 1000)
            return {
                "provider": self.provider_name,
                "healthy": False,
                "latency_ms": latency,
                "message": str(exc),
            }

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        queries = self._build_queries(query, industry, city, country)
        seen_urls: set[str] = set()
        yielded = 0

        for search_query in queries:
            if yielded >= max_results:
                break
            for engine_cfg in _ENGINES:
                if yielded >= max_results:
                    break
                try:
                    items = await self._search_engine(search_query, engine_cfg)
                except Exception as exc:
                    logger.warning(
                        "WebSearch engine %r failed: %s",
                        engine_cfg["name"],
                        exc,
                    )
                    continue

                for item in items:
                    if yielded >= max_results:
                        break
                    url = item.get("url", "")
                    domain = self._extract_domain(url)
                    if domain and domain in seen_urls:
                        continue
                    if domain:
                        seen_urls.add(domain)

                    result = self._item_to_result(item, industry, city, country)
                    if result:
                        yield result
                        yielded += 1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=_DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=20.0,
            )
        return self._client

    async def _search_engine(
        self,
        query: str,
        engine: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        await self._limiter.acquire()
        client = await self._get_client()
        params = {engine["param"]: query}
        resp = await client.get(engine["url"], params=params, timeout=20)
        resp.raise_for_status()
        return self._parse_engine_html(resp.text, engine)

    @staticmethod
    def _parse_engine_html(
        html: str,
        engine: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(html, "html.parser")
        results: List[Dict[str, Any]] = []

        for block in soup.select(engine["result_sel"]):
            title_tag = block.select_one(engine["title_sel"])
            link_tag = block.select_one(engine["link_sel"])
            snippet_tag = block.select_one(engine["snippet_sel"])

            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = (
                link_tag.get(engine.get("link_attr", "href"), "") if link_tag else ""
            )
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            results.append(
                {
                    "title": title,
                    "url": href,
                    "snippet": snippet,
                    "engine": engine["name"],
                }
            )

        return results

    @staticmethod
    def _build_queries(
        query: str,
        industry: Optional[str],
        city: Optional[str],
        country: Optional[str],
    ) -> List[str]:
        """Build 1-3 targeted search queries."""
        base_parts = [
            p for p in [industry, "businesses", "in", city, country] if p
        ]
        queries = [" ".join(base_parts)]
        if query and query not in " ".join(base_parts):
            queries.append(f"{query} {industry or ''} {city or ''}".strip())
        if industry and city:
            queries.append(f'"{industry}" "{city}" contact site')
        return [q for q in queries if q.strip()]

    @staticmethod
    def _extract_domain(url: str) -> Optional[str]:
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower() or None
        except Exception:
            return None

    @staticmethod
    def _item_to_result(
        item: Dict[str, Any],
        industry: Optional[str],
        city: Optional[str],
        country: Optional[str],
    ) -> Optional[BusinessResult]:
        title = (item.get("title") or "").strip()
        if not title:
            return None

        url = item.get("url", "")
        snippet = item.get("snippet", "")

        # Attempt to extract phone from snippet
        phone_match = re.search(
            r"\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}", snippet
        )
        phone = phone_match.group(0) if phone_match else None

        # Clean website URL to just scheme + netloc
        parsed = urlparse(url)
        website = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url or None

        source_id = parsed.netloc or url or title

        return BusinessResult(
            name=title,
            address=None,
            city=city,
            state=None,
            country=country,
            phone=phone,
            email=None,
            website_url=website,
            category=industry,
            source="web_search",
            source_id=source_id,
            raw_data=item,
        )

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "WebSearchProvider":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
