"""
Google Maps scraper provider — no API key required.

Pass 1: Playwright scrapes Google Maps search for real business names,
        addresses, categories, ratings and Google Maps URLs.
Pass 2: For each business, run a targeted DDG search by exact name + city
        to find their official website, phone and email.
Pass 3: If website found, scrape it for additional contact info.

Works worldwide for any city/country/industry.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Domains that are NOT business websites
_SKIP_DOMAINS = {
    "google.com", "google.com.pk", "maps.google.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com",
    "yelp.com", "tripadvisor.com", "yellowpages.com",
    "linkedin.com", "youtube.com", "tiktok.com",
    "wikipedia.org", "reddit.com", "quora.com",
    "zomato.com", "foursquare.com", "booking.com",
    "justdial.com", "sulekha.com", "lookup.pk", "hamariweb.com",
    # Business directory aggregators
    "bizsouthasia.com", "findglocal.com", "cybo.com", "bizapedia.com",
    "manta.com", "bbb.org", "chamberofcommerce.com", "hotfrog.com",
    "brownbook.net", "n49.com", "cylex.us", "showmelocal.com",
    "businessyab.com", "whereis.com", "locanto.com", "whitepages.com",
    "superpages.com", "citysearch.com", "mapquest.com",
    "whodoyou.com", "fyple.com", "getfave.com", "opendi.com",
    "near-place.com", "pk.near-place.com", "placedigger.com",
    "nicelocal.com", "2gis.com", "openstreetmap.org",
}

_PLACEHOLDER_EMAIL_DOMAINS = {
    "example.com", "domain.com", "email.com", "test.com", "yourdomain.com",
}
_PLACEHOLDER_EMAIL_LOCALS = {
    "noreply", "no-reply", "donotreply", "example", "test",
    "user", "you", "your", "name", "email", "admin", "info2",
}


class GoogleMapsProvider(BaseDiscoveryProvider):
    """
    Two-pass discovery: Google Maps → real business list,
    then DDG → website/email/phone for each business.
    No API key needed. Works worldwide.
    """

    _RATE_LIMIT_RPM = 20

    @property
    def provider_name(self) -> str:
        return "google_maps"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
            return True
        except ImportError:
            logger.warning("google_maps: playwright not installed")
            return False

    async def health_check(self) -> Dict[str, Any]:
        try:
            results = []
            async for r in self.discover("restaurant", city="London", max_results=2):
                results.append(r)
                if len(results) >= 2:
                    break
            return {"provider": "google_maps", "healthy": len(results) > 0, "count": len(results)}
        except Exception as exc:
            return {"provider": "google_maps", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        if not city and not country:
            logger.warning("google_maps: city or country required")
            return

        loc = f"{city} {country}" if city and country else (city or country or "")
        search_query = f"{query} in {loc}"

        try:
            businesses = await self._scrape_maps(search_query, max_results)
        except Exception as exc:
            logger.error("google_maps scrape failed: %s", exc)
            return

        seen: set[str] = set()
        for biz in businesses:
            name = biz.get("name", "").strip()
            if not name or name in seen:
                continue
            seen.add(name)

            # Pass 2: find website + contact via DDG for this exact business
            website, phone, email = await self._find_contact(name, city or "", country or "")

            # Pass 3: scrape website for more contact info if found
            if website and (not email or not phone):
                scraped_phone, scraped_email = await self._scrape_website(website)
                phone = phone or scraped_phone
                email = email or scraped_email

            yield BusinessResult(
                name=name,
                address=biz.get("address"),
                city=city,
                state=None,
                country=country,
                phone=phone or biz.get("phone"),
                email=email,
                website_url=website,
                category=biz.get("category") or industry,
                source="google_maps",
                source_id=biz.get("maps_url") or name,
                latitude=biz.get("lat"),
                longitude=biz.get("lng"),
                raw_data={**biz, "website": website, "phone": phone, "email": email},
            )
            # Small delay between businesses so DDG doesn't rate-limit
            await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # Pass 1 — Scrape Google Maps listing page
    # ------------------------------------------------------------------

    async def _scrape_maps(self, query: str, max_results: int) -> List[Dict[str, Any]]:
        from playwright.async_api import async_playwright

        url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
        results: List[Dict[str, Any]] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                ctx = await browser.new_context(user_agent=_UA)
                page = await ctx.new_page()
                await page.route("**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf}", lambda r: r.abort())

                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(4000)

                # Scroll to load more cards
                scroll_rounds = min(15, (max_results // 4) + 3)
                for _ in range(scroll_rounds):
                    count = await page.locator(".Nv2PK").count()
                    if count >= max_results:
                        break
                    try:
                        await page.locator('[role="feed"]').evaluate("el => el.scrollTop += 1200")
                    except Exception:
                        break
                    await page.wait_for_timeout(1200)

                cards = await page.locator(".Nv2PK").all()
                logger.info("google_maps: %d cards found for %r", len(cards), query)

                seen_names: set[str] = set()
                for card in cards[: max_results * 2]:
                    if len(results) >= max_results:
                        break
                    try:
                        biz = await self._parse_card(card)
                        if biz and biz["name"] not in seen_names:
                            seen_names.add(biz["name"])
                            results.append(biz)
                    except Exception as exc:
                        logger.debug("google_maps: card parse error: %s", exc)
            finally:
                await browser.close()

        return results

    @staticmethod
    async def _parse_card(card: Any) -> Optional[Dict[str, Any]]:
        name_el = card.locator(".qBF1Pd").first
        name = (await name_el.inner_text(timeout=2000)).strip()
        if not name:
            return None

        rating = None
        try:
            rt = await card.locator("span.MW4etd").first.inner_text(timeout=500)
            rating = float(rt.strip())
        except Exception:
            pass

        category = address = phone = None
        try:
            texts = await card.locator(".W4Efsd span").all_inner_texts()
            clean = [t.strip() for t in texts if t.strip() and t.strip() not in ("·", "⋅", "•", "")]
            for t in clean:
                if not category and re.match(r"^[A-Za-z\s&/]+$", t) and len(t) > 3:
                    category = t
                if not address:
                    if re.match(r"^[\d.]+\([\d,]+\)$", t):
                        continue
                    if re.search(r"Street|Road|Ave|Block|Plot|Lane|Rd|Colony|Town|Sector|Phase|Shop|DHA|F-\d|G-\d", t, re.I):
                        address = t
                    elif re.search(r"\d", t) and len(t) > 6 and not re.match(r"^[\d.,()\s]+$", t):
                        address = t
                if not phone and re.match(r"^\+?[\d\s\-().]{7,20}$", t):
                    phone = re.sub(r"[\s\-()]", "", t)
        except Exception:
            pass

        maps_url = None
        try:
            maps_url = await card.locator("a.hfpxzc").first.get_attribute("href", timeout=500)
        except Exception:
            pass

        # Extract lat/lng from maps URL
        lat = lng = None
        if maps_url:
            m = re.search(r"@([-\d.]+),([-\d.]+)", maps_url)
            if m:
                lat, lng = float(m.group(1)), float(m.group(2))

        return {
            "name": name,
            "rating": rating,
            "category": category,
            "address": address,
            "phone": phone,
            "maps_url": maps_url,
            "lat": lat,
            "lng": lng,
        }

    # ------------------------------------------------------------------
    # Pass 2 — Find website/phone/email via DDG search
    # ------------------------------------------------------------------

    async def _find_contact(
        self, name: str, city: str, country: str
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Search DDG for '{name} {city} official website' and extract contact info."""
        excl = "-site:facebook.com -site:instagram.com -site:yelp.com -site:tripadvisor.com"
        query = f'"{name}" {city} official website contact {excl}'
        try:
            results = await asyncio.get_event_loop().run_in_executor(
                None, self._ddg_search, query, 5
            )
        except Exception as exc:
            logger.debug("google_maps DDG lookup failed for %r: %s", name, exc)
            return None, None, None

        website = phone = email = None

        for item in results:
            url = item.get("href", "")
            snippet = (item.get("body") or "")
            parsed = urlparse(url)
            domain = parsed.netloc.lower().lstrip("www.")

            # Skip directory/aggregator domains
            if any(domain == s or domain.endswith("." + s) for s in _SKIP_DOMAINS):
                continue
            if ".gov" in domain or ".edu" in domain:
                continue

            # Accept as website if not already found
            if not website and parsed.netloc:
                website = f"{parsed.scheme}://{parsed.netloc}"

            # Extract phone from snippet
            if not phone:
                for ph in re.findall(r"\+?[\d][\d\s\-().]{7,18}\d", snippet):
                    cleaned = re.sub(r"[\s\-()]", "", ph)
                    if len(cleaned) >= 7:
                        phone = cleaned
                        break

            # Extract email from snippet
            if not email:
                for em in re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", snippet):
                    parts = em.lower().split("@")
                    if len(parts) == 2:
                        if parts[0] in _PLACEHOLDER_EMAIL_LOCALS:
                            continue
                        if parts[1] in _PLACEHOLDER_EMAIL_DOMAINS:
                            continue
                        email = em
                        break

            if website and phone and email:
                break

        return website, phone, email

    @staticmethod
    def _ddg_search(query: str, max_results: int) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as exc:
            logger.debug("DDG search error: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Pass 3 — Scrape business website for contact info
    # ------------------------------------------------------------------

    @staticmethod
    async def _scrape_website(
        website_url: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """Quick scrape of homepage + /contact for phone and email."""
        phone = email = None
        try:
            hdrs = {"User-Agent": "Mozilla/5.0 (compatible; BI-Platform/1.0)"}
            base = website_url.rstrip("/")
            urls_to_try = [base, f"{base}/contact", f"{base}/contact-us"]
            async with httpx.AsyncClient(
                follow_redirects=True, timeout=5.0, headers=hdrs, verify=False
            ) as client:
                for url in urls_to_try:
                    try:
                        r = await client.get(url)
                        html = r.text

                        # Email via mailto: (most reliable)
                        for m in re.finditer(r'href=["\']mailto:([^"\'?\s]+)["\']', html, re.I):
                            em = m.group(1).lower()
                            parts = em.split("@")
                            if len(parts) == 2 and parts[0] not in _PLACEHOLDER_EMAIL_LOCALS and parts[1] not in _PLACEHOLDER_EMAIL_DOMAINS:
                                email = em
                                break

                        # Phone via tel: href
                        if not phone:
                            for m in re.finditer(r'href=["\']tel:(\+[\d\s\-().]{7,25})["\']', html, re.I):
                                ph = re.sub(r"[\s\-()]", "", m.group(1))
                                if len(ph) >= 7:
                                    phone = ph
                                    break

                        # Fallback: regex phone starting with +
                        if not phone:
                            for ph in re.findall(r"\+\d{1,3}[\d\s\-().]{6,18}\d", html):
                                cleaned = re.sub(r"[\s\-()]", "", ph)
                                if len(cleaned) >= 9:
                                    phone = cleaned
                                    break

                        if email and phone:
                            break
                    except Exception:
                        continue
        except Exception:
            pass
        return phone, email
