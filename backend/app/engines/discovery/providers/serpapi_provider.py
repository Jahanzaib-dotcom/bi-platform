"""SerpAPI Google Maps discovery provider (requires SERPAPI_KEY)."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_SERPAPI_BASE = "https://serpapi.com/search"
_RATE_LIMIT_RPM = 100


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


class SerpAPIProvider(BaseDiscoveryProvider):
    """
    Queries Google Maps via SerpAPI to discover local businesses.

    Requires the environment variable ``SERPAPI_KEY``.  If the key is absent
    the provider will skip itself gracefully (``validate_config`` returns
    ``False`` and ``discover`` yields nothing).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._api_key = api_key or os.environ.get("SERPAPI_KEY", "")
        self._limiter = _RateLimiter(_RATE_LIMIT_RPM)
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # BaseDiscoveryProvider interface
    # ------------------------------------------------------------------

    @property
    def provider_name(self) -> str:
        return "serpapi"

    @property
    def rate_limit(self) -> int:
        return _RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return bool(self._api_key)

    async def health_check(self) -> Dict[str, Any]:
        if not self._api_key:
            return {
                "provider": self.provider_name,
                "healthy": False,
                "latency_ms": 0,
                "message": "SERPAPI_KEY not configured",
            }
        start = time.monotonic()
        try:
            client = await self._get_client()
            resp = await client.get(
                f"{_SERPAPI_BASE}",
                params={
                    "engine": "google_maps",
                    "q": "coffee shop",
                    "api_key": self._api_key,
                },
                timeout=10,
            )
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
        if not self._api_key:
            logger.info("SerpAPI provider skipped: SERPAPI_KEY not set")
            return

        search_query = self._build_query(query, industry, city)
        yielded = 0
        start_index = 0

        while yielded < max_results:
            batch_size = min(20, max_results - yielded)
            try:
                items = await self._fetch_local_results(
                    search_query, country, start_index, batch_size
                )
            except Exception as exc:
                logger.error("SerpAPI request failed: %s", exc)
                break

            if not items:
                break

            for item in items:
                if yielded >= max_results:
                    break
                result = self._parse_local_result(item, industry, city, country)
                if result:
                    yield result
                    yielded += 1

            if len(items) < batch_size:
                # Fewer results than requested — end of results
                break

            start_index += batch_size

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    async def _fetch_local_results(
        self,
        query: str,
        country: Optional[str],
        start: int,
        limit: int,
    ) -> List[Dict[str, Any]]:
        await self._limiter.acquire()
        client = await self._get_client()

        params: Dict[str, Any] = {
            "engine": "google_maps",
            "q": query,
            "api_key": self._api_key,
            "start": start,
            "num": limit,
            "hl": "en",
        }
        if country:
            params["gl"] = country[:2].lower()

        resp = await client.get(_SERPAPI_BASE, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        return data.get("local_results", [])

    @staticmethod
    def _build_query(
        query: str,
        industry: Optional[str],
        city: Optional[str],
    ) -> str:
        parts = []
        if industry:
            parts.append(industry)
        if query:
            parts.append(query)
        if city:
            parts.append(city)
        return " ".join(parts) if parts else query

    @staticmethod
    def _parse_local_result(
        item: Dict[str, Any],
        industry: Optional[str],
        city: Optional[str],
        country: Optional[str],
    ) -> Optional[BusinessResult]:
        name = (item.get("title") or "").strip()
        if not name:
            return None

        address = item.get("address", "")
        phone = item.get("phone", "")
        website = item.get("website", "")
        place_id = item.get("place_id", "") or item.get("data_id", "")

        # Try to extract city/state from address
        parsed_city = city
        parsed_state = None
        if address:
            parts = [p.strip() for p in address.split(",")]
            if len(parts) >= 2:
                # Last part is often country or zip+country; second-to-last is city/state
                parsed_city = parsed_city or parts[-2].split()[0] if parts[-2] else city

        category = (
            item.get("type")
            or (item.get("types") or [None])[0]
            or industry
        )

        rating = item.get("rating")
        reviews = item.get("reviews")

        return BusinessResult(
            name=name,
            address=address or None,
            city=parsed_city,
            state=parsed_state,
            country=country,
            phone=phone or None,
            email=None,
            website_url=website or None,
            category=category,
            source="serpapi",
            source_id=place_id or None,
            raw_data={
                "place_id": place_id,
                "rating": rating,
                "reviews": reviews,
                "address": address,
                "serpapi_raw": item,
            },
        )

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "SerpAPIProvider":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()
