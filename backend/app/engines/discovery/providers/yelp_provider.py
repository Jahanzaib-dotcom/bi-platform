"""
Yelp Fusion API discovery provider.

Uses Yelp Business Search to find real local businesses with phone, website,
address, and category. Free tier: 500 calls/day, no credit card required.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
_MAX_PER_REQUEST = 50  # Yelp max per call


class YelpProvider(BaseDiscoveryProvider):
    """
    Discovers businesses using the Yelp Fusion API.
    Returns real local businesses with phone, website, address from Yelp.
    Requires YELP_API_KEY in environment.
    """

    @property
    def provider_name(self) -> str:
        return "yelp"

    @property
    def rate_limit(self) -> int:
        return 30

    async def validate_config(self) -> bool:
        from app.core.config import settings
        key = getattr(settings, "YELP_API_KEY", "")
        if not key:
            logger.debug("yelp: skipped (YELP_API_KEY not set)")
            return False
        return True

    async def health_check(self) -> Dict[str, Any]:
        from app.core.config import settings
        key = getattr(settings, "YELP_API_KEY", "")
        if not key:
            return {"provider": "yelp", "healthy": False, "message": "API key not configured"}
        try:
            results = await self._search("restaurant", "New York", key, limit=1, offset=0)
            return {"provider": "yelp", "healthy": True, "count": len(results)}
        except Exception as exc:
            return {"provider": "yelp", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        from app.core.config import settings
        key = getattr(settings, "YELP_API_KEY", "")
        if not key:
            logger.warning("yelp: no API key, skipping")
            return

        # Yelp Fusion only covers US, Canada, and select major cities worldwide.
        # For unsupported regions it returns 400 — we log and gracefully return.
        location = f"{city}, {country}" if city and country else (city or country or "New York, NY")
        logger.info("yelp: searching query=%r location=%r max=%d", query, location, max_results)

        fetched = 0
        offset = 0

        while fetched < max_results:
            batch_limit = min(_MAX_PER_REQUEST, max_results - fetched)
            try:
                businesses = await self._search(query, location, key, limit=batch_limit, offset=offset)
            except Exception as exc:
                logger.error("Yelp search failed: %s", exc)
                break

            if not businesses:
                break

            for biz in businesses:
                result = self._parse_business(biz, city, country, industry)
                if result:
                    yield result
                    await asyncio.sleep(0)

            fetched += len(businesses)
            offset += len(businesses)

            if len(businesses) < batch_limit:
                break  # no more results

            await asyncio.sleep(0.5)  # be kind to rate limits

    async def _search(
        self,
        query: str,
        location: str,
        api_key: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                _SEARCH_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                params={
                    "term": query,
                    "location": location,
                    "limit": limit,
                    "offset": offset,
                    "sort_by": "best_match",
                },
            )

            if resp.status_code == 400:
                # Yelp doesn't support all regions — log clearly so the user understands
                logger.warning(
                    "Yelp 400: location not supported or invalid. "
                    "Yelp only covers US/Canada and select major cities. "
                    "query=%s location=%s response=%s",
                    query, location, resp.text[:200],
                )
                return []

            if resp.status_code != 200:
                logger.error("Yelp API error %d: %s", resp.status_code, resp.text[:200])
                return []

            data = resp.json()
            return data.get("businesses", [])

    @staticmethod
    def _parse_business(
        biz: Dict[str, Any],
        city: Optional[str],
        country: Optional[str],
        industry: Optional[str],
    ) -> Optional[BusinessResult]:
        name = (biz.get("name") or "").strip()
        if not name:
            return None

        if biz.get("is_closed"):
            return None

        phone = biz.get("display_phone") or biz.get("phone")
        # biz.get("url") is the Yelp listing page, not the real business website.
        # Don't save it as website_url — it causes the scraper to fetch yelp.com.
        website = None

        location_data = biz.get("location") or {}
        address_parts = location_data.get("display_address") or []
        address = ", ".join(address_parts) if address_parts else None
        biz_city = location_data.get("city") or city
        biz_state = location_data.get("state")
        biz_country = location_data.get("country") or country

        categories = biz.get("categories") or []
        category = categories[0].get("title") if categories else industry

        return BusinessResult(
            name=name,
            address=address,
            city=biz_city,
            state=biz_state,
            country=biz_country,
            phone=phone,
            email=None,
            website_url=website,
            category=category,
            source="yelp",
            source_id=biz.get("id", name),
            raw_data=biz,
        )

    async def aclose(self) -> None:
        pass

    async def __aenter__(self) -> "YelpProvider":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass
