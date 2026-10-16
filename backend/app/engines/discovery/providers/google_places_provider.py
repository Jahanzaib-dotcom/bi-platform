"""
Google Places API (New) discovery provider.

Uses the Places API Text Search to find real businesses with full contact info
including phone, website, address, and rating — sourced from Google My Business.

Pricing: $0.032/request. Google gives $200 free credit/month (~6,000 free searches).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_PLACE_DETAIL_URL = "https://places.googleapis.com/v1/places/{place_id}"

_FIELD_MASK = ",".join([
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.primaryTypeDisplayName",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.addressComponents",
])


class GooglePlacesProvider(BaseDiscoveryProvider):
    """
    Discovers businesses using Google Places API (New) Text Search.
    Returns real businesses with phone, website, address from Google My Business.
    Requires GOOGLE_PLACES_API_KEY in environment.
    """

    @property
    def provider_name(self) -> str:
        return "google_places"

    @property
    def rate_limit(self) -> int:
        return 30  # 30 RPM to stay safe

    async def validate_config(self) -> bool:
        from app.core.config import settings
        key = getattr(settings, "GOOGLE_PLACES_API_KEY", "")
        if not key:
            logger.debug("google_places: skipped (GOOGLE_PLACES_API_KEY not set)")
            return False
        return True

    async def health_check(self) -> Dict[str, Any]:
        from app.core.config import settings
        key = getattr(settings, "GOOGLE_PLACES_API_KEY", "")
        if not key:
            return {"provider": "google_places", "healthy": False, "message": "API key not configured"}
        try:
            results = await self._text_search("restaurant", "New York", key, max_results=1)
            return {"provider": "google_places", "healthy": True, "count": len(results)}
        except Exception as exc:
            return {"provider": "google_places", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        from app.core.config import settings
        key = getattr(settings, "GOOGLE_PLACES_API_KEY", "")
        if not key:
            logger.warning("google_places: no API key, skipping")
            return

        location = f"{city}, {country}" if city and country else (city or country or "")
        search_query = f"{query} in {location}" if location else query

        try:
            places = await self._text_search(search_query, location, key, max_results=max_results)
        except Exception as exc:
            logger.error("Google Places search failed: %s", exc)
            return

        for place in places:
            result = self._parse_place(place, city, country, industry)
            if result:
                yield result
                await asyncio.sleep(0)

    async def _text_search(
        self,
        query: str,
        location: str,
        api_key: str,
        max_results: int = 20,
    ) -> List[Dict[str, Any]]:
        """Call Places API Text Search, handle pagination up to max_results."""
        all_places: List[Dict[str, Any]] = []
        page_token: Optional[str] = None

        async with httpx.AsyncClient(timeout=15) as client:
            while len(all_places) < max_results:
                payload: Dict[str, Any] = {
                    "textQuery": query,
                    "maxResultCount": min(20, max_results - len(all_places)),
                    "languageCode": "en",
                }
                if page_token:
                    payload["pageToken"] = page_token

                resp = await client.post(
                    _TEXT_SEARCH_URL,
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Goog-Api-Key": api_key,
                        "X-Goog-FieldMask": _FIELD_MASK,
                    },
                )

                if resp.status_code != 200:
                    logger.error("Google Places API error %d: %s", resp.status_code, resp.text[:200])
                    break

                data = resp.json()
                places = data.get("places", [])
                all_places.extend(places)

                page_token = data.get("nextPageToken")
                if not page_token or not places:
                    break

                await asyncio.sleep(2)  # Google requires a short delay before using nextPageToken

        return all_places

    @staticmethod
    def _parse_place(
        place: Dict[str, Any],
        city: Optional[str],
        country: Optional[str],
        industry: Optional[str],
    ) -> Optional[BusinessResult]:
        name = (place.get("displayName") or {}).get("text", "").strip()
        if not name:
            return None

        # Skip permanently closed businesses
        if place.get("businessStatus") == "PERMANENTLY_CLOSED":
            return None

        phone = place.get("internationalPhoneNumber") or place.get("nationalPhoneNumber")
        website = place.get("websiteUri")
        address = place.get("formattedAddress", "")
        category = (place.get("primaryTypeDisplayName") or {}).get("text") or industry

        # Extract city and country from addressComponents
        parsed_city = city
        parsed_country = country
        for comp in place.get("addressComponents", []):
            types = comp.get("types", [])
            if "locality" in types and not parsed_city:
                parsed_city = comp.get("longText", city)
            if "country" in types and not parsed_country:
                parsed_country = comp.get("longText", country)

        return BusinessResult(
            name=name,
            address=address,
            city=parsed_city,
            state=None,
            country=parsed_country,
            phone=phone,
            email=None,  # Places API doesn't expose email — scraper will get it from website
            website_url=website,
            category=category,
            source="google_places",
            source_id=place.get("id", name),
            raw_data=place,
        )

    async def aclose(self) -> None:
        pass

    async def __aenter__(self) -> "GooglePlacesProvider":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass
