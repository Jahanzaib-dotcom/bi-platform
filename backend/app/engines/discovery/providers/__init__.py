"""Discovery providers package — exports get_provider factory."""
from __future__ import annotations

from app.engines.discovery.base import BaseDiscoveryProvider
from app.core.config import settings


def get_provider(name: str) -> BaseDiscoveryProvider:
    """
    Return an initialised provider instance by name.
    All key-based providers read their API key from settings internally.
    Raises ValueError for unknown or unconfigured providers.
    """
    n = name.lower().strip()

    if n == "duckduckgo":
        from app.engines.discovery.providers.duckduckgo_provider import DuckDuckGoProvider
        return DuckDuckGoProvider()

    if n == "nominatim":
        from app.engines.discovery.providers.nominatim_provider import NominatimProvider
        return NominatimProvider()

    if n == "overpass":
        from app.engines.discovery.providers.overpass_provider import OverpassProvider
        return OverpassProvider()

    if n == "google_places":
        if not settings.GOOGLE_PLACES_API_KEY:
            raise ValueError("GOOGLE_PLACES_API_KEY is not configured in .env")
        from app.engines.discovery.providers.google_places_provider import GooglePlacesProvider
        return GooglePlacesProvider()

    if n == "google_maps":
        from app.engines.discovery.providers.google_maps_provider import GoogleMapsProvider
        return GoogleMapsProvider()

    if n == "yelp":
        if not settings.YELP_API_KEY:
            raise ValueError("YELP_API_KEY is not configured in .env")
        from app.engines.discovery.providers.yelp_provider import YelpProvider
        return YelpProvider()

    if n == "serpapi":
        if not settings.SERPAPI_KEY:
            raise ValueError("SERPAPI_KEY is not configured in .env")
        from app.engines.discovery.providers.serpapi_provider import SerpAPIProvider
        return SerpAPIProvider()

    if n in ("web_search", "websearch"):
        from app.engines.discovery.providers.web_search_provider import WebSearchProvider
        return WebSearchProvider()

    if n == "instagram":
        from app.engines.discovery.providers.instagram_provider import InstagramProvider
        return InstagramProvider()

    if n == "facebook":
        from app.engines.discovery.providers.facebook_provider import FacebookProvider
        return FacebookProvider()

    if n == "reddit":
        from app.engines.discovery.providers.reddit_provider import RedditProvider
        return RedditProvider()

    if n in ("ecommerce_brands", "daraz", "ecommerce"):
        from app.engines.discovery.providers.ecommerce_provider import EcommerceProvider
        return EcommerceProvider()

    if n in ("freelance", "upwork", "freelancer", "fiverr"):
        from app.engines.discovery.providers.freelance_provider import FreelanceProvider
        return FreelanceProvider()

    raise ValueError(f"Unknown provider: '{name}'")


__all__ = ["get_provider"]
