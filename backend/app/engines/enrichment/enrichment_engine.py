"""
Multi-pass business enrichment engine.

Pass 1 – Website crawl (homepage + /contact + /about)
Pass 2 – Social media discovery (pattern matching + meta tags + JSON-LD)
Pass 3 – Extended contact extraction (email, phone, WhatsApp)
Pass 4 – Structured data (JSON-LD, schema.org, Open Graph, meta)
Pass 5 – Completeness scoring and field confidence
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Social URL patterns — ordered most-specific first
# ---------------------------------------------------------------------------

_SOCIAL_PATTERNS: Dict[str, re.Pattern] = {
    "facebook_url": re.compile(
        r"https?://(?:www\.)?facebook\.com/(?!sharer|share|dialog|plugins|pages/category)"
        r"[a-zA-Z0-9./_\-?=%&]+",
        re.IGNORECASE,
    ),
    "instagram_url": re.compile(
        r"https?://(?:www\.)?instagram\.com/[a-zA-Z0-9._]+/?",
        re.IGNORECASE,
    ),
    "linkedin_url": re.compile(
        r"https?://(?:www\.)?linkedin\.com/(?:in|company|school)/[a-zA-Z0-9\-_%/]+/?",
        re.IGNORECASE,
    ),
    "twitter_url": re.compile(
        r"https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+/?",
        re.IGNORECASE,
    ),
    "tiktok_url": re.compile(
        r"https?://(?:www\.)?tiktok\.com/@[a-zA-Z0-9._]+/?",
        re.IGNORECASE,
    ),
    "youtube_url": re.compile(
        r"https?://(?:www\.)?youtube\.com/(?:channel|c|user|@)[a-zA-Z0-9._\-/]+/?",
        re.IGNORECASE,
    ),
    "pinterest_url": re.compile(
        r"https?://(?:www\.)?pinterest\.(?:com|co\.[a-z]{2})/[a-zA-Z0-9._\-/]+/?",
        re.IGNORECASE,
    ),
}

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_MAILTO_RE = re.compile(r'href=["\']mailto:([^"\'?\s]+)["\']', re.IGNORECASE)
_TEL_RE = re.compile(r'href=["\']tel:(\+[\d\s\-().]{7,25})["\']', re.IGNORECASE)
_PHONE_RE = re.compile(r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}")

_WHATSAPP_RE = re.compile(
    r"https?://(?:api\.whatsapp\.com/send\?phone=|wa\.me/)(\+?[\d]{7,15})", re.IGNORECASE
)

_LAT_RE = re.compile(r'"latitude"\s*:\s*([-\d.]+)', re.IGNORECASE)
_LNG_RE = re.compile(r'"longitude"\s*:\s*([-\d.]+)', re.IGNORECASE)

_JUNK_EMAIL_LOCAL = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "example", "test", "postmaster", "mailer-daemon",
    "user", "admin", "webmaster", "support", "info2",
    "youremail", "your-email", "name", "email",
}

# Placeholder/example domains — never real business emails
_JUNK_EMAIL_DOMAINS = {
    "example.com", "example.org", "example.net",
    "domain.com", "yourdomain.com", "email.com",
    "test.com", "sample.com", "placeholder.com",
    "mailinator.com", "tempmail.com", "guerrillamail.com",
}

_INTERNAL_PATHS = ["/contact", "/contact-us", "/about", "/about-us", "/reach-us", "/find-us"]

# Fields that count toward completeness (weight = 1 each unless otherwise noted)
_COMPLETENESS_FIELDS = [
    "name", "category", "description", "address", "city", "country",
    "phone", "email", "website_url",
    "latitude", "longitude",
    "facebook_url", "instagram_url", "linkedin_url", "twitter_url",
    "tiktok_url", "youtube_url",
    "phone2", "email2", "whatsapp",
    "contact_page_url", "about_page_url",
    "rating", "review_count", "opening_hours", "services",
    "logo_url", "founded_year", "company_size",
]


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

class EnrichmentResult:
    """Holds all fields gathered across all passes."""

    def __init__(self) -> None:
        self.phone2: Optional[str] = None
        self.whatsapp: Optional[str] = None
        self.email2: Optional[str] = None
        self.contact_page_url: Optional[str] = None
        self.about_page_url: Optional[str] = None
        self.careers_page_url: Optional[str] = None
        self.facebook_url: Optional[str] = None
        self.instagram_url: Optional[str] = None
        self.linkedin_url: Optional[str] = None
        self.twitter_url: Optional[str] = None
        self.tiktok_url: Optional[str] = None
        self.youtube_url: Optional[str] = None
        self.pinterest_url: Optional[str] = None
        self.description: Optional[str] = None
        self.logo_url: Optional[str] = None
        self.latitude: Optional[float] = None
        self.longitude: Optional[float] = None
        self.google_maps_url: Optional[str] = None
        self.rating: Optional[float] = None
        self.review_count: Optional[int] = None
        self.opening_hours: Optional[Dict[str, Any]] = None
        self.services: Optional[List[str]] = None
        self.founded_year: Optional[int] = None
        self.company_size: Optional[str] = None
        self.completeness_score: float = 0.0
        self.enrichment_data: Dict[str, Any] = {}

    def to_patch(self) -> Dict[str, Any]:
        """Return only non-None values as a dict suitable for updating a Business."""
        patch = {}
        for key, val in self.__dict__.items():
            if key in ("completeness_score", "enrichment_data"):
                continue
            if val is not None:
                patch[key] = val
        return patch


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class EnrichmentEngine:
    """Multi-pass enrichment for a single business."""

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    async def enrich(self, business_dict: Dict[str, Any]) -> EnrichmentResult:
        """Run all enrichment passes and return result."""
        result = EnrichmentResult()
        website_url = business_dict.get("website_url")

        pages: Dict[str, str] = {}  # path → html

        # Pass 1 — fetch website pages or run zero-website deep contact enrichment
        if website_url:
            pages = await self._fetch_pages(website_url)
        else:
            await self._enrich_no_website(business_dict, result)

        # Pass 2 — extract from all fetched HTML
        all_html = "\n".join(pages.values())
        if all_html:
            self._extract_social(all_html, result)
            self._extract_contacts(all_html, result, business_dict)
            self._extract_structured_data(all_html, result)
            self._extract_internal_links(pages, website_url or "", result)
            self._extract_logo(all_html, website_url or "", result)

        # Pass 3 — fill completeness score
        result.completeness_score = self._score(business_dict, result)

        # Pass 4 — record source metadata
        result.enrichment_data = {
            "pages_fetched": list(pages.keys()) if pages else ["no-website-social-enrichment"],
            "enriched_at": datetime.now(timezone.utc).isoformat(),
            "fields_added": [k for k, v in result.to_patch().items() if v is not None],
            "zero_website": not bool(website_url),
        }

        return result

    async def _enrich_no_website(self, business_dict: Dict[str, Any], result: EnrichmentResult) -> None:
        """Deep contact enrichment for businesses with NO websites (Instagram/Facebook sellers)."""
        existing_phone = business_dict.get("phone")
        existing_email = business_dict.get("email")
        country = business_dict.get("country")
        city = business_dict.get("city")
        name = business_dict.get("name")
        desc = business_dict.get("description") or ""

        # 1. Extract from description / pitch snippet
        if desc:
            clean_desc = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", desc, flags=re.IGNORECASE)
            if not existing_email and not result.email2:
                for em in _EMAIL_RE.findall(clean_desc):
                    em_low = em.lower().strip()
                    if not any(ign in em_low for ign in ("instagram.com", "facebook.com", "example.com")):
                        result.email2 = em_low
                        break

            if not existing_phone and not result.whatsapp:
                from app.engines.contact.validator import validate_phone, PhoneStatus
                m_wa = re.search(r"(?:https?://)?(?:www\.)?wa\.me/(\+?\d+)", desc)
                if m_wa:
                    result.whatsapp = f"https://wa.me/{m_wa.group(1).lstrip('+')}"
                else:
                    m_ph = re.search(r"(?:whatsapp|wa|ph|call|phone|contact|📲|📞)[:\s]+(\+?[\d\s\-()]{7,20})", desc, re.IGNORECASE)
                    if m_ph:
                        pv = validate_phone(m_ph.group(1).strip(), country=country, city=city)
                        if pv.status == PhoneStatus.VALID and pv.e164:
                            result.whatsapp = f"https://wa.me/{pv.e164.lstrip('+')}"

        # 2. Targeted search snippet pass if contact details are still missing
        if name and ((not existing_email and not result.email2) or (not existing_phone and not result.whatsapp)):
            loc_str = city or country or ""
            query = f'"{name}" {loc_str} ("@gmail.com" OR "whatsapp" OR "wa.me")'
            try:
                loop = asyncio.get_event_loop()
                def _sync_ddg():
                    from ddgs import DDGS
                    with DDGS() as ddgs:
                        return list(ddgs.text(query, max_results=3))
                snippets = await loop.run_in_executor(None, _sync_ddg)
                combined_snips = " ".join(f"{s.get('title', '')} {s.get('body', '')}" for s in snippets)
                clean_snips = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", combined_snips, flags=re.IGNORECASE)

                if not existing_email and not result.email2:
                    for em in _EMAIL_RE.findall(clean_snips):
                        em_low = em.lower().strip()
                        if not any(ign in em_low for ign in ("instagram.com", "facebook.com", "example.com", "cloudflare.com")):
                            result.email2 = em_low
                            break

                if not existing_phone and not result.whatsapp:
                    from app.engines.contact.validator import validate_phone, PhoneStatus
                    m_wa = re.search(r"(?:https?://)?(?:www\.)?wa\.me/(\+?\d+)", clean_snips)
                    if m_wa:
                        result.whatsapp = f"https://wa.me/{m_wa.group(1).lstrip('+')}"
                    else:
                        m_ph = re.search(r"(?:whatsapp|wa|ph|call|phone|contact|📲|📞)[:\s]+(\+?[\d\s\-()]{7,20})", clean_snips, re.IGNORECASE)
                        if m_ph:
                            pv = validate_phone(m_ph.group(1).strip(), country=country, city=city)
                            if pv.status == PhoneStatus.VALID and pv.e164:
                                result.whatsapp = f"https://wa.me/{pv.e164.lstrip('+')}"
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Pass 1 — page fetching
    # -------------------------------------------------------------------------

    async def _fetch_pages(self, base_url: str) -> Dict[str, str]:
        """Fetch homepage + /contact + /about concurrently, return {path: html}."""
        if not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url

        pages: Dict[str, str] = {}
        paths_to_try = ["/"] + _INTERNAL_PATHS

        async def _fetch(path: str) -> None:
            url = urljoin(base_url, path)
            try:
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=self._timeout,
                    headers={"User-Agent": "BI-Platform-Enricher/2.0"},
                    verify=False,
                ) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                        pages[path] = resp.text[:120_000]  # cap at 120KB per page
            except Exception:
                pass

        # Fetch homepage first, then try internals concurrently
        await _fetch("/")
        if pages.get("/"):
            await asyncio.gather(*[_fetch(p) for p in _INTERNAL_PATHS])
        return pages

    # -------------------------------------------------------------------------
    # Pass 2 — social media extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_social(html: str, result: EnrichmentResult) -> None:
        for field, pattern in _SOCIAL_PATTERNS.items():
            if getattr(result, field):
                continue
            match = pattern.search(html)
            if match:
                url = match.group(0).rstrip("?#").rstrip("/")
                # Skip very short/generic matches
                parsed = urlparse(url)
                if len(parsed.path.strip("/")) >= 2:
                    setattr(result, field, url)

        # WhatsApp
        if not result.whatsapp:
            wa_match = _WHATSAPP_RE.search(html)
            if wa_match:
                number = re.sub(r"[^\d+]", "", wa_match.group(1))
                if not number.startswith("+"):
                    number = "+" + number
                result.whatsapp = number

    # -------------------------------------------------------------------------
    # Pass 3 — contact extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_contacts(html: str, result: EnrichmentResult, existing: Dict[str, Any]) -> None:
        existing_email = existing.get("email", "")
        existing_phone = existing.get("phone", "")

        def _is_junk_email(e: str) -> bool:
            e = e.lower().strip()
            parts = e.split("@")
            if len(parts) != 2:
                return True
            local, domain = parts[0], parts[1]
            if local in _JUNK_EMAIL_LOCAL:
                return True
            if domain in _JUNK_EMAIL_DOMAINS:
                return True
            # Reject obvious placeholder patterns like user@domain.com, you@email.com
            if local in ("you", "your", "yours", "me", "my", "someone"):
                return True
            return False

        # Emails from mailto: hrefs (high confidence)
        emails = list(dict.fromkeys(_MAILTO_RE.findall(html)))
        emails = [e.lower().strip() for e in emails if "@" in e and not _is_junk_email(e)]
        # Regex fallback
        if len(emails) < 2:
            re_emails = [e.lower() for e in _EMAIL_RE.findall(html) if not _is_junk_email(e)]
            for e in re_emails:
                if e not in emails:
                    emails.append(e)

        for email in emails:
            if email == existing_email:
                continue
            if not result.email2:
                result.email2 = email
                break

        # Phones from tel: hrefs (high confidence)
        phones = list(dict.fromkeys(_TEL_RE.findall(html)))
        phones = [re.sub(r"[^\d+]", "", p) for p in phones if p.startswith("+")]
        phones = [p for p in phones if len(p) >= 8]
        # Regex fallback
        if len(phones) < 2:
            for match in _PHONE_RE.finditer(html):
                normalized = re.sub(r"[^\d+]", "", match.group(0))
                if normalized.startswith("+") and len(normalized) >= 8 and normalized not in phones:
                    phones.append(normalized)

        for phone in phones:
            if phone == existing_phone:
                continue
            if not result.phone2:
                result.phone2 = phone
                break

    # -------------------------------------------------------------------------
    # Pass 4 — structured data (JSON-LD, meta, Open Graph)
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_structured_data(html: str, result: EnrichmentResult) -> None:
        import json as _json

        # JSON-LD blocks
        jsonld_blocks = re.findall(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html,
            re.DOTALL | re.IGNORECASE,
        )
        for block in jsonld_blocks:
            try:
                data = _json.loads(block.strip())
                if isinstance(data, list):
                    for item in data:
                        EnrichmentEngine._apply_jsonld(item, result)
                else:
                    EnrichmentEngine._apply_jsonld(data, result)
            except Exception:
                pass

        # Open Graph description
        if not result.description:
            og_desc = re.search(
                r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']{20,})["\']',
                html, re.IGNORECASE,
            )
            if og_desc:
                result.description = og_desc.group(1).strip()[:500]

        # Meta description fallback
        if not result.description:
            meta_desc = re.search(
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{20,})["\']',
                html, re.IGNORECASE,
            )
            if meta_desc:
                result.description = meta_desc.group(1).strip()[:500]

        # Lat/lng from structured data or Google Maps embed
        if not result.latitude:
            lat_m = _LAT_RE.search(html)
            lng_m = _LNG_RE.search(html)
            if lat_m and lng_m:
                try:
                    result.latitude = float(lat_m.group(1))
                    result.longitude = float(lng_m.group(1))
                except ValueError:
                    pass

        # Google Maps embed
        if not result.google_maps_url:
            maps_m = re.search(r'https://(?:maps\.google\.com|www\.google\.com/maps)[^\s"\'<>]+', html)
            if maps_m:
                result.google_maps_url = maps_m.group(0)[:500]

    @staticmethod
    def _apply_jsonld(data: Dict[str, Any], result: EnrichmentResult) -> None:
        if not isinstance(data, dict):
            return
        schema_type = data.get("@type", "")

        # Description
        if not result.description and data.get("description"):
            result.description = str(data["description"])[:500]

        # Logo
        if not result.logo_url:
            logo = data.get("logo")
            if isinstance(logo, dict):
                result.logo_url = logo.get("url") or logo.get("contentUrl")
            elif isinstance(logo, str):
                result.logo_url = logo

        # Rating
        if not result.rating:
            agg = data.get("aggregateRating") or {}
            if isinstance(agg, dict):
                rv = agg.get("ratingValue") or agg.get("ratingCount")
                if rv:
                    try:
                        result.rating = float(rv)
                    except (ValueError, TypeError):
                        pass
                rc = agg.get("reviewCount") or agg.get("ratingCount")
                if rc and not result.review_count:
                    try:
                        result.review_count = int(rc)
                    except (ValueError, TypeError):
                        pass

        # Founded year
        if not result.founded_year:
            fy = data.get("foundingDate") or data.get("foundedYear")
            if fy:
                m = re.search(r"\d{4}", str(fy))
                if m:
                    result.founded_year = int(m.group(0))

        # Number of employees → company_size
        if not result.company_size:
            emp = data.get("numberOfEmployees")
            if isinstance(emp, dict):
                val = emp.get("value") or emp.get("minValue")
                if val:
                    result.company_size = str(val)
            elif emp:
                result.company_size = str(emp)

        # Opening hours
        if not result.opening_hours and data.get("openingHoursSpecification"):
            result.opening_hours = data["openingHoursSpecification"]

        # Geo coordinates
        geo = data.get("geo") or {}
        if isinstance(geo, dict):
            if not result.latitude and geo.get("latitude"):
                try:
                    result.latitude = float(geo["latitude"])
                    result.longitude = float(geo.get("longitude", 0))
                except (ValueError, TypeError):
                    pass

        # Social URLs from sameAs
        same_as = data.get("sameAs") or []
        if isinstance(same_as, str):
            same_as = [same_as]
        for url in same_as:
            for field, pattern in _SOCIAL_PATTERNS.items():
                if not getattr(result, field) and pattern.match(url):
                    setattr(result, field, url)

    # -------------------------------------------------------------------------
    # Internal link discovery
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_internal_links(pages: Dict[str, str], base_url: str, result: EnrichmentResult) -> None:
        home_html = pages.get("/", "")
        if not home_html:
            return

        href_pattern = re.compile(r'href=["\']([^"\'#?]+)["\']', re.IGNORECASE)
        for match in href_pattern.finditer(home_html):
            href = match.group(1).lower().strip("/")
            if "contact" in href and not result.contact_page_url:
                result.contact_page_url = urljoin(base_url, match.group(1))
            elif "about" in href and not result.about_page_url:
                result.about_page_url = urljoin(base_url, match.group(1))
            elif ("career" in href or "jobs" in href or "work-with" in href) and not result.careers_page_url:
                result.careers_page_url = urljoin(base_url, match.group(1))

    # -------------------------------------------------------------------------
    # Logo extraction
    # -------------------------------------------------------------------------

    @staticmethod
    def _extract_logo(html: str, base_url: str, result: EnrichmentResult) -> None:
        if result.logo_url:
            return
        # Open Graph image
        og_image = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if og_image:
            img_url = og_image.group(1)
            result.logo_url = img_url if img_url.startswith("http") else urljoin(base_url, img_url)
            return
        # <img> with logo/brand in class or id
        logo_img = re.search(
            r'<img[^>]+(?:id|class|alt)=["\'][^"\']*(?:logo|brand)[^"\']*["\'][^>]+src=["\']([^"\']+)["\']',
            html, re.IGNORECASE,
        )
        if logo_img:
            src = logo_img.group(1)
            result.logo_url = src if src.startswith("http") else urljoin(base_url, src)

    # -------------------------------------------------------------------------
    # Completeness scoring
    # -------------------------------------------------------------------------

    @staticmethod
    def _score(existing: Dict[str, Any], result: EnrichmentResult) -> float:
        total = len(_COMPLETENESS_FIELDS)
        found = 0
        result_patch = result.to_patch()
        for field in _COMPLETENESS_FIELDS:
            val = existing.get(field) or result_patch.get(field)
            if val is not None and val != "" and val != [] and val != {}:
                found += 1
        return round((found / total) * 100, 1)
