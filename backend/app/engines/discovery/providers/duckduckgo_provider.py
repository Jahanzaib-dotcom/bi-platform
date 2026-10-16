"""DuckDuckGo discovery provider using the ddgs library (no API key required)."""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

# Domains that are directories / aggregators, not actual businesses
_JUNK_DOMAINS = {
    # Review / listing sites
    "yelp.com", "tripadvisor.com", "yellowpages.com", "thumbtack.com",
    "angi.com", "angieslist.com", "homeadvisor.com", "houzz.com",
    "bbb.org", "manta.com", "bizapedia.com", "chamberofcommerce.com",
    "trustpilot.com", "foursquare.com", "mapquest.com",
    "citysearch.com", "superpages.com", "whitepages.com",
    "businessyab.com", "cylex.us", "showmelocal.com", "n49.com",
    # Social / search
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "linkedin.com", "google.com", "bing.com", "yahoo.com",
    "wikipedia.org", "wikihow.com", "reddit.com", "quora.com",
    "pinterest.com", "tiktok.com", "youtube.com",
    # Jobs
    "indeed.com", "glassdoor.com", "monster.com", "ziprecruiter.com",
    # Food delivery
    "opentable.com", "grubhub.com", "doordash.com", "ubereats.com",
    "zomato.com", "swiggy.com", "talabat.com", "foodpanda.com",
    # Travel / hotels
    "booking.com", "expedia.com", "hotels.com", "airbnb.com",
    "agoda.com", "kayak.com", "trivago.com",
    # Health directories
    "healthgrades.com", "zocdoc.com", "vitals.com", "ratemds.com",
    "practo.com", "lybrate.com",
    # Legal directories
    "avvo.com", "martindale.com", "lawyers.com", "justia.com",
    # Real estate
    "apartmentlist.com", "zillow.com", "realtor.com", "trulia.com",
    # Pakistan / India / South Asia directories
    "hamariweb.com", "brandsofworld.com", "justdial.com", "sulekha.com",
    "magicpin.in", "cardekho.com", "olx.com", "olx.com.pk",
    "pakwheels.com", "rozee.pk", "lookup.pk", "rehbar.pk",
    "karachi.com", "lahore.com", "islamabad.com",
    "graana.com", "zameen.com", "imlaak.com",
    # Other regional directories
    "hotfrog.com", "brownbook.net", "kompass.com", "europages.com",
    "yelp.ie", "yelp.co.uk", "yelp.com.au",
}

# Title patterns that indicate a directory page, not a business
_JUNK_TITLE_PATTERNS = re.compile(
    r"best\s+\d+|top\s+\d+|\d+\s+best|\breviews\b|list of|near me|"
    r"directory|yellowpages|yelp|tripadvisor|find a |search results|"
    r"updated \d{4}|near you|\ball\b.{0,10}\brestaurant|"
    r"restaurant list|phone numbers|addresses|important phone|"
    r"\»\s+entertainment|things to do|visit \w+|"
    r"barber shops? in |salons? in |restaurants? in |clinics? in |"
    r"businesses? in |listing.{0,10}in |find.{0,20}in |search.{0,20}in |"
    r"add your business|business directory|local business|"
    r"^trusted\s+|^authentic\s+|^award.winning\s+|^eat and drink|^visit our|"
    r"tax\s+return|revenue\s+board|government|gos\.pk|gov\.|"
    r"lookup\.pk|rehbar\.pk|hamariweb|",
    re.IGNORECASE,
)

# Generic single-word or short page-title names that are not business names
_JUNK_NAMES = {
    "home", "contact", "contact us", "about", "about us", "welcome",
    "services", "index", "main", "blog", "news", "page", "site", "website",
    "patient care", "our services", "get directions", "directions",
    "schedule", "appointments", "make appointment", "book now",
    "dentists", "dentist", "plumbers", "plumber", "lawyers", "doctor",
    "doctors", "restaurants", "restaurant", "salons", "barbershops",
    "barbers", "clinics", "gyms", "hotels", "pharmacies",
    "us", "we", "our", "me", "team",
}

# Snippets that show the result is NOT a business website
_JUNK_SNIPPET_PATTERNS = re.compile(
    r"add your business|find local business|list of .{0,30}in |"
    r"\d+ results? found|browse \d+|showing \d+|"
    r"short dramas?|movies?|web series|episodes?|streaming|"
    r"sign up for free|create an account|register your business",
    re.IGNORECASE,
)

# Starts-with patterns that mark keyword stuffing, not real names
_KEYWORD_NAME_PATTERNS = re.compile(
    r"^(best|top|#\d|no\.\s*\d|\d+\s|award|premier|leading|trusted|"
    r"affordable|professional|licensed|certified|experienced)\b",
    re.IGNORECASE,
)

# Names that are just keyword phrases (too long = description, not a name)
_MAX_NAME_WORDS = 8


class DuckDuckGoProvider(BaseDiscoveryProvider):
    """Discovers businesses using DuckDuckGo web search via the ddgs library."""

    _RATE_LIMIT_RPM = 10

    @property
    def provider_name(self) -> str:
        return "duckduckgo"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        try:
            results = await self._search("test restaurant", max_results=1)
            return {"provider": "duckduckgo", "healthy": True, "message": "OK", "sample_result_count": len(results)}
        except Exception as exc:
            return {"provider": "duckduckgo", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        queries = self._build_queries(query, country, city)
        seen_urls: set = set()
        seen_names: set = set()
        # Fetch 5x the requested amount per query to survive junk filtering losses
        per_query = min(100, max(50, (max_results * 5) // len(queries)))
        yielded = 0

        for search_query in queries:
            if yielded >= max_results:
                break
            try:
                raw_results = await self._search(search_query, max_results=per_query)
            except Exception as exc:
                logger.warning("DuckDuckGo search failed: %s", exc)
                continue

            for item in raw_results:
                if yielded >= max_results:
                    break

                url = item.get("href", "")
                parsed = urlparse(url)
                domain = parsed.netloc.lower().lstrip("www.")

                # Skip junk domains
                if any(domain == junk or domain.endswith("." + junk) for junk in _JUNK_DOMAINS):
                    continue
                # Skip government/edu sites (not businesses)
                if ".gov" in domain or ".edu" in domain or "gos.pk" in domain:
                    continue

                # Skip junk titles
                title = (item.get("title") or "").strip()
                if not title or _JUNK_TITLE_PATTERNS.search(title):
                    continue

                # Skip if snippet reveals it's a directory/non-business page
                snippet = (item.get("body") or "").strip()
                if snippet and _JUNK_SNIPPET_PATTERNS.search(snippet):
                    continue

                # Skip already-seen URLs
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                # Clean up title — strip " | Location" and " - tagline" suffixes
                name = self._clean_title(title)

                # Skip generic single-word page titles
                name_key = name.lower().strip()
                if name_key in _JUNK_NAMES:
                    continue

                # Skip keyword-stuffed SEO names
                if _KEYWORD_NAME_PATTERNS.search(name):
                    continue

                # Skip names that are just bracket-wrapped domains like [www.foo.org]
                if name.startswith("[") or name.startswith("("):
                    continue

                # Skip overly long "names" (they're really keyword phrases)
                if len(name.split()) > _MAX_NAME_WORDS:
                    continue

                # Skip if we already have this name
                if name_key in seen_names:
                    continue
                seen_names.add(name_key)

                result = self._parse_result(item, name, industry, city, country)
                if result:
                    yield result
                    yielded += 1
                    await asyncio.sleep(0)

    @staticmethod
    def _clean_title(title: str) -> str:
        """Strip page-title noise and normalize to a business name."""
        # Remove page-prefix words like "Contact ", "About ", "Home - "
        for prefix in ("contact ", "about ", "home ", "welcome to ", "visit "):
            if title.lower().startswith(prefix):
                title = title[len(prefix):]
                break
        # Remove trailing separators and everything after
        for sep in [" | ", " - ", " :: ", " — ", " – "]:
            if sep in title:
                parts = title.split(sep)
                # Keep first part only if it's reasonably short (a business name)
                if len(parts[0].strip()) >= 3:
                    title = parts[0].strip()
                    break
        # Strip leading separator artifacts
        title = re.sub(r'^[\|\-\–\—:]+\s*', '', title).strip()
        return title

    @staticmethod
    def _build_queries(query: str, country: Optional[str], city: Optional[str]) -> List[str]:
        """Build diverse targeted queries to find individual business websites."""
        loc = f"{city}" if city else (country or "")
        loc_full = f"{city} {country}" if city and country else loc
        excl = "-site:yelp.com -site:tripadvisor.com -site:yellowpages.com"
        return [
            # Contact page of actual businesses
            f'{query} {loc_full} contact us email {excl}',
            # About pages of businesses
            f'{query} {loc_full} about us official website {excl}',
            # Phone/WhatsApp targeting
            f'{query} {loc_full} phone WhatsApp address {excl}',
            # Different keyword angle to get fresh results
            f'{query} {loc_full} services booking appointment {excl}',
            # Name + city style searches
            f'{query} {loc} website portfolio {excl} -inurl:list -inurl:directory',
        ]

    async def _search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query, max_results)

    @staticmethod
    def _sync_search(query: str, max_results: int) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=min(max_results, 100)))
                return results
        except Exception as exc:
            logger.warning("ddgs search error: %s", exc)
            return []

    @staticmethod
    def _parse_result(
        item: Dict[str, Any],
        name: str,
        industry: Optional[str],
        city: Optional[str],
        country: Optional[str],
    ) -> Optional[BusinessResult]:
        if not name:
            return None

        url = item.get("href") or item.get("url") or ""
        snippet = item.get("body") or item.get("snippet") or ""

        # Extract email from snippet — reject placeholders
        _PLACEHOLDER_DOMAINS = {"example.com", "domain.com", "email.com", "yourdomain.com", "test.com", "sample.com"}
        _PLACEHOLDER_LOCALS = {"noreply", "no-reply", "example", "test", "donotreply", "user", "you", "your", "name", "email", "admin"}
        email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", snippet)
        email = email_match.group(0) if email_match else None
        if email:
            _parts = email.lower().split("@")
            if len(_parts) == 2 and (_parts[0] in _PLACEHOLDER_LOCALS or _parts[1] in _PLACEHOLDER_DOMAINS):
                email = None

        # Extract phone from snippet
        phone_match = re.search(r"\+?[\d][\d\s\-().]{7,20}", snippet)
        phone = phone_match.group(0).strip() if phone_match else None

        # Extract address
        address_match = re.search(
            r"\d+\s+[A-Z][a-zA-Z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Way|Place|Pl)",
            snippet,
        )
        address = address_match.group(0) if address_match else None

        # Clean website URL to domain only
        parsed = urlparse(url)
        website = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else url or None

        return BusinessResult(
            name=name,
            address=address,
            city=city,
            state=None,
            country=country,
            phone=phone,
            email=email,
            website_url=website,
            category=industry,
            source="duckduckgo",
            source_id=url or name,
            raw_data=item,
        )

    async def aclose(self) -> None:
        pass

    async def __aenter__(self) -> "DuckDuckGoProvider":
        return self

    async def __aexit__(self, *_: Any) -> None:
        pass
