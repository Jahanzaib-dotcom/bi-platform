"""
OpenStreetMap / Nominatim discovery provider.

Uses Nominatim structured search to find physical businesses in a city.
Most businesses in OSM have NO website — making this the best source for
finding undigitised businesses that need web services.
Free, no API key required.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# OSM amenity values to search — one request per amenity type
_AMENITY_MAP: Dict[str, List[str]] = {
    "restaurant":  ["restaurant", "cafe", "fast_food", "bar", "pub", "bakery"],
    "food":        ["restaurant", "cafe", "fast_food", "bakery", "ice_cream"],
    "retail":      ["shop"],
    "healthcare":  ["clinic", "dentist", "pharmacy", "veterinary"],
    "beauty":      ["hairdresser", "beauty"],
    "automotive":  ["fuel", "car_wash", "car_repair"],
    "hotel":       ["hotel", "hostel", "guest_house", "motel"],
    "fitness":     ["gym", "fitness_centre", "sports_centre"],
    "education":   ["school", "college", "university"],
    "finance":     ["bank"],
    "default":     ["restaurant", "cafe", "fast_food", "clinic", "hairdresser",
                    "pharmacy", "hotel", "gym", "bank", "fuel"],
}

_MAX_PER_AMENITY = 50  # Nominatim max results per request


class NominatimProvider(BaseDiscoveryProvider):
    """
    Finds physical businesses from OpenStreetMap — most without websites.
    Best source for targeting offline/undigitised businesses.
    """

    _RATE_LIMIT_RPM = 20

    @property
    def provider_name(self) -> str:
        return "nominatim"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=10) as c:
                r = await c.get(_NOMINATIM_SEARCH, params={"q": "London", "format": "json", "limit": 1})
                ok = r.status_code == 200
            return {"provider": "nominatim", "healthy": ok, "message": "OK" if ok else f"HTTP {r.status_code}"}
        except Exception as exc:
            return {"provider": "nominatim", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        if not city and not country:
            logger.warning("nominatim: city or country required for discovery")
            return

        amenities = self._resolve_amenities(industry, query)
        seen: set[str] = set()
        yielded = 0

        for amenity in amenities:
            if yielded >= max_results:
                break

            elements = await self._search_amenity(amenity, city, country)
            await asyncio.sleep(1.1)  # Nominatim ToS: 1 request/second

            for el in elements:
                if yielded >= max_results:
                    break
                name = (el.get("name") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)

                result = self._element_to_result(el, amenity, industry, city, country)
                if result:
                    yield result
                    yielded += 1

    async def _search_amenity(
        self,
        amenity: str,
        city: Optional[str],
        country: Optional[str],
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "amenity": amenity,
            "format": "json",
            "limit": _MAX_PER_AMENITY,
            "extratags": 1,
            "addressdetails": 1,
            "namedetails": 1,
        }
        if city:
            params["city"] = city
        if country:
            params["country"] = country

        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=15) as c:
                r = await c.get(_NOMINATIM_SEARCH, params=params)
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.error("Nominatim search error for amenity=%r: %s", amenity, exc)
            return []

    @staticmethod
    def _resolve_amenities(industry: Optional[str], query: str) -> List[str]:
        combined = f"{industry or ''} {query}".lower()
        for key, tags in _AMENITY_MAP.items():
            if key in combined:
                return tags
        return _AMENITY_MAP["default"]

    @staticmethod
    def _element_to_result(
        el: Dict[str, Any],
        amenity: str,
        industry: Optional[str],
        city: Optional[str],
        country: Optional[str],
    ) -> Optional[BusinessResult]:
        name = (el.get("name") or "").strip()
        if not name:
            return None

        extras = el.get("extratags") or {}
        address_obj = el.get("address") or {}

        website = extras.get("website") or extras.get("contact:website") or extras.get("url")
        phone = extras.get("phone") or extras.get("contact:phone") or extras.get("mobile")
        email = extras.get("email") or extras.get("contact:email")

        biz_city = (
            address_obj.get("city")
            or address_obj.get("town")
            or address_obj.get("village")
            or city
        )
        biz_state = address_obj.get("state")
        biz_country = address_obj.get("country") or country

        road = address_obj.get("road") or address_obj.get("street") or ""
        house = address_obj.get("house_number") or ""
        address = f"{house} {road}".strip() or None

        category = extras.get("amenity") or extras.get("shop") or amenity or industry
        osm_id = f"{el.get('osm_type', 'node')}:{el.get('osm_id', el.get('place_id', ''))}"

        return BusinessResult(
            name=name,
            address=address,
            city=biz_city,
            state=biz_state,
            country=biz_country,
            phone=phone,
            email=email,
            website_url=website or None,
            category=category,
            source="nominatim",
            source_id=osm_id,
            raw_data={"extratags": extras, "address": address_obj, "osm_id": osm_id},
        )
