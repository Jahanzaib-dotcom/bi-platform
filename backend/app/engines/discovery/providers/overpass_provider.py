"""
OSM Overpass API discovery provider — PRIMARY source.

Strategy:
  1. Resolve city → bounding-box via Nominatim (one request, cached per run).
  2. Query Overpass with that bbox for each amenity category.
  3. If bbox resolution fails, fall back to area["name"=...] query.
  4. Try mirror endpoints on timeout/error.

Returns name, address, phone, website, email, lat/lng, opening_hours from OSM tags.
Both short (phone/email/website) and contact: tag variants are read.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

_NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"

_USER_AGENT = "BI-Platform/1.0 (business-discovery-bot; open-source)"

_HEADERS = {
    "User-Agent": _USER_AGENT,
}

# OSM amenity/shop tags per industry keyword
_AMENITY_MAP: Dict[str, List[str]] = {
    "restaurant":  ["restaurant", "cafe", "fast_food", "bar", "pub", "bakery", "food_court"],
    "food":        ["restaurant", "cafe", "fast_food", "bakery", "ice_cream", "confectionery"],
    "retail":      ["supermarket", "convenience", "clothes", "shoes", "electronics", "hardware"],
    "shop":        ["supermarket", "convenience", "clothes", "shoes", "electronics", "hardware"],
    "healthcare":  ["clinic", "dentist", "pharmacy", "veterinary", "hospital", "doctors"],
    "clinic":      ["clinic", "dentist", "doctors", "pharmacy"],
    "beauty":      ["hairdresser", "beauty", "massage", "nail_salon"],
    "salon":       ["hairdresser", "beauty", "nail_salon"],
    "automotive":  ["fuel", "car_wash", "car_repair", "tyres"],
    "hotel":       ["hotel", "hostel", "guest_house", "motel"],
    "fitness":     ["gym", "fitness_centre", "sports_centre"],
    "gym":         ["gym", "fitness_centre", "sports_centre"],
    "education":   ["school", "college", "university", "language_school", "driving_school"],
    "finance":     ["bank", "money_transfer", "bureau_de_change"],
    "bank":        ["bank", "money_transfer"],
    "default":     ["restaurant", "cafe", "clinic", "pharmacy", "hairdresser",
                    "hotel", "gym", "bank", "fuel", "supermarket"],
}

_TIMEOUT = 30.0
_MAX_PER_QUERY = 100


class OverpassProvider(BaseDiscoveryProvider):
    """
    Finds physical businesses from OSM Overpass API.
    Primary source — returns verified OSM data with lat/lng.
    """

    _RATE_LIMIT_RPM = 30

    @property
    def provider_name(self) -> str:
        return "overpass"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        query = '[out:json][timeout:10]; node["amenity"="cafe"](51.5,-0.1,51.51,-0.09); out 1;'
        try:
            data = await self._run_query(query)
            ok = "elements" in data
            return {"provider": "overpass", "healthy": ok, "message": "OK" if ok else "Bad response"}
        except Exception as exc:
            return {"provider": "overpass", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        if not city and not country:
            logger.warning("overpass: city or country required")
            return

        amenities = self._resolve_amenities(industry, query)

        # Step 1: try to get bounding box from Nominatim
        bbox = await self._resolve_bbox(city, country)
        use_bbox = bbox is not None

        seen: set[str] = set()
        yielded = 0

        for amenity in amenities:
            if yielded >= max_results:
                break

            try:
                if use_bbox:
                    elements = await self._query_by_bbox(amenity, bbox)  # type: ignore[arg-type]
                    if not elements:
                        # bbox gave nothing — try area name fallback
                        elements = await self._query_by_area(amenity, city, country)
                else:
                    elements = await self._query_by_area(amenity, city, country)
            except Exception as exc:
                logger.warning("overpass: query failed for amenity=%r: %s", amenity, exc)
                elements = []

            await asyncio.sleep(1.1)  # Overpass ToS: be polite

            for el in elements:
                if yielded >= max_results:
                    break
                tags = el.get("tags") or {}
                name = (tags.get("name") or "").strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                result = self._element_to_result(el, amenity, industry, city, country)
                if result:
                    yield result
                    yielded += 1

    # ------------------------------------------------------------------
    # Overpass queries
    # ------------------------------------------------------------------

    async def _query_by_bbox(
        self,
        amenity: str,
        bbox: Tuple[float, float, float, float],
    ) -> List[Dict[str, Any]]:
        """Query all nodes/ways/relations with given amenity inside a bounding box."""
        s, w, n, e = bbox
        # Include both amenity= and shop= tags
        query = (
            f'[out:json][timeout:25];'
            f'('
            f'  node["amenity"="{amenity}"]({s},{w},{n},{e});'
            f'  way["amenity"="{amenity}"]({s},{w},{n},{e});'
            f'  node["shop"="{amenity}"]({s},{w},{n},{e});'
            f'  way["shop"="{amenity}"]({s},{w},{n},{e});'
            f');'
            f'out center {_MAX_PER_QUERY};'
        )
        data = await self._run_query(query)
        return data.get("elements", [])

    async def _query_by_area(
        self,
        amenity: str,
        city: Optional[str],
        country: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Fallback: area["name"=...] query."""
        area_name = city or country or ""
        query = (
            f'[out:json][timeout:25];'
            f'area["name"="{area_name}"]->.searchArea;'
            f'('
            f'  node["amenity"="{amenity}"](area.searchArea);'
            f'  way["amenity"="{amenity}"](area.searchArea);'
            f'  node["shop"="{amenity}"](area.searchArea);'
            f'  way["shop"="{amenity}"](area.searchArea);'
            f');'
            f'out center {_MAX_PER_QUERY};'
        )
        data = await self._run_query(query)
        return data.get("elements", [])

    async def _run_query(self, query: str) -> Dict[str, Any]:
        """Try each endpoint in order, return on first success."""
        last_exc: Exception = RuntimeError("No endpoints tried")
        for endpoint in _OVERPASS_ENDPOINTS:
            try:
                async with httpx.AsyncClient(
                    headers=_HEADERS,
                    timeout=_TIMEOUT,
                    follow_redirects=True,
                ) as client:
                    resp = await client.post(endpoint, data={"data": query})
                    resp.raise_for_status()
                    return resp.json()
            except Exception as exc:
                logger.debug("overpass endpoint %s failed: %s", endpoint, exc)
                last_exc = exc
                await asyncio.sleep(0.5)
        raise last_exc

    # ------------------------------------------------------------------
    # Nominatim bbox resolution (one call per city, not per business)
    # ------------------------------------------------------------------

    async def _resolve_bbox(
        self,
        city: Optional[str],
        country: Optional[str],
    ) -> Optional[Tuple[float, float, float, float]]:
        """Return (south, west, north, east) for the city, or None on failure."""
        if not city:
            return None
        params: Dict[str, Any] = {
            "q": f"{city}{', ' + country if country else ''}",
            "format": "json",
            "limit": 1,
            "featuretype": "city,town",
        }
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": _USER_AGENT},
                timeout=10.0,
            ) as client:
                resp = await client.get(_NOMINATIM_SEARCH, params=params)
                resp.raise_for_status()
                results = resp.json()
            if not results:
                return None
            bb = results[0].get("boundingbox")
            if bb and len(bb) == 4:
                s, n, w, e = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
                return (s, w, n, e)
        except Exception as exc:
            logger.debug("overpass: Nominatim bbox lookup failed: %s", exc)
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_amenities(industry: Optional[str], query: str) -> List[str]:
        combined = f"{industry or ''} {query}".lower()
        for key, tags in _AMENITY_MAP.items():
            if key in combined:
                return tags
        return _AMENITY_MAP["default"]

    @staticmethod
    def _get_tag(tags: Dict[str, Any], *keys: str) -> Optional[str]:
        """Return first non-empty value from a list of tag keys."""
        for key in keys:
            val = tags.get(key)
            if val:
                return str(val).strip()
        return None

    @classmethod
    def _element_to_result(
        cls,
        el: Dict[str, Any],
        amenity: str,
        industry: Optional[str],
        city: Optional[str],
        country: Optional[str],
    ) -> Optional[BusinessResult]:
        tags = el.get("tags") or {}
        name = (tags.get("name") or "").strip()
        if not name:
            return None

        # Read both short and contact: variants
        phone = cls._get_tag(tags, "phone", "contact:phone", "mobile", "contact:mobile")
        email = cls._get_tag(tags, "email", "contact:email")
        website = cls._get_tag(tags, "website", "contact:website", "url", "contact:url")
        addr_full = cls._get_tag(tags, "addr:full")
        addr_street = cls._get_tag(tags, "addr:street") or ""
        addr_housenumber = cls._get_tag(tags, "addr:housenumber") or ""
        address = addr_full or f"{addr_housenumber} {addr_street}".strip() or None

        biz_city = cls._get_tag(tags, "addr:city") or city
        biz_state = cls._get_tag(tags, "addr:state")
        biz_country = cls._get_tag(tags, "addr:country") or country

        # Coordinates: nodes have lat/lon directly; ways have center
        center = el.get("center") or {}
        lat = el.get("lat") or center.get("lat")
        lon = el.get("lon") or center.get("lon")

        category = (
            tags.get("amenity")
            or tags.get("shop")
            or tags.get("leisure")
            or amenity
            or industry
        )
        osm_id = f"{el.get('type', 'node')}:{el.get('id', '')}"

        # Normalize phone: remove spaces/dashes but keep + prefix
        if phone:
            phone = re.sub(r"[\s\-()]", "", phone)
            if not phone.startswith("+"):
                phone = None  # no country code — not usable

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
            source="overpass",
            source_id=osm_id,
            latitude=float(lat) if lat is not None else None,
            longitude=float(lon) if lon is not None else None,
            raw_data={"tags": tags, "osm_id": osm_id},
        )
