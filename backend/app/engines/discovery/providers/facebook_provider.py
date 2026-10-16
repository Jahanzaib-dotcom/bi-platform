"""Facebook business pages and marketplace seller discovery provider.

Finds verified business pages, local service providers, and shops on Facebook
with active phone and WhatsApp contacts, flagging those without websites for web
development outreach.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

PK_MOBILE_PREFIXES = set([f"03{d:02d}" for d in range(0, 50)] + ["0355"])

_EXCLUDED_FB_PATHS = {
    "login", "help", "pages", "groups", "events", "watch", "gaming", "marketplace",
    "policies", "privacy", "terms", "recover", "search", "share", "dialog", "hashtag"
}


def clean_phone_number(
    raw_phone: str,
    country: Optional[str] = None,
    city: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Clean and validate phone numbers, prioritizing E.164 and WhatsApp formatting across regions."""
    if not raw_phone:
        return None, None
    digits = re.sub(r"\D", "", raw_phone)
    if not digits or len(digits) < 7:
        return None, None

    # Pakistani mobile: 923xxxxxxxxx (12 digits) or 03xxxxxxxxx (11 digits)
    if digits.startswith("92") and len(digits) == 12:
        prefix = "0" + digits[2:5]
        if prefix in PK_MOBILE_PREFIXES:
            formatted = f"+92 {digits[2:5]} {digits[5:]}"
            wa_link = f"https://wa.me/{digits}"
            return formatted, wa_link
    elif digits.startswith("03") and len(digits) == 11:
        prefix = digits[:4]
        if prefix in PK_MOBILE_PREFIXES:
            formatted = f"+92 {digits[1:4]} {digits[4:]}"
            wa_link = f"https://wa.me/92{digits[1:]}"
            return formatted, wa_link

    # International phone validation via PhoneValidator
    try:
        from app.engines.contact.validator import validate_phone, PhoneStatus
        pv = validate_phone(raw_phone, country=country, city=city)
        if pv.status == PhoneStatus.VALID and pv.e164:
            import phonenumbers
            try:
                p = phonenumbers.parse(pv.e164, None)
                formatted = phonenumbers.format_number(p, phonenumbers.PhoneNumberFormat.INTERNATIONAL)
            except Exception:
                formatted = pv.e164
            wa_link = f"https://wa.me/{pv.e164.lstrip('+')}"
            return formatted, wa_link
    except Exception:
        pass

    # UAE fallback
    if digits.startswith("9715") and len(digits) == 12:
        formatted = f"+971 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        return formatted, f"https://wa.me/{digits}"
    elif digits.startswith("05") and len(digits) == 10:
        pure_971 = f"971{digits[1:]}"
        formatted = f"+971 {digits[1:3]} {digits[3:6]} {digits[6:]}"
        return formatted, f"https://wa.me/{pure_971}"

    # International standard: 10 to 14 digits
    if 10 <= len(digits) <= 14:
        if digits.startswith("1") and len(digits) == 11:
            formatted = f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            return formatted, f"https://wa.me/{digits}"
        formatted = f"+{digits}"
        wa_link = f"https://wa.me/{digits}"
        return formatted, wa_link

    return None, None


class FacebookProvider(BaseDiscoveryProvider):
    """Discovers Facebook business pages with phone, WhatsApp, and location data."""

    _RATE_LIMIT_RPM = 15

    @property
    def provider_name(self) -> str:
        return "facebook"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        try:
            results = await self._search("site:facebook.com salon", max_results=1)
            return {
                "provider": "facebook",
                "healthy": True,
                "message": "OK",
                "sample_result_count": len(results),
            }
        except Exception as exc:
            return {"provider": "facebook", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        queries = self._build_queries(query, country, city, industry)
        seen_pages: set[str] = set()
        yielded = 0
        per_query = min(50, max(20, (max_results * 2) // max(1, len(queries))))

        for search_query in queries:
            if yielded >= max_results:
                break

            try:
                raw_results = await self._search(search_query, max_results=per_query)
            except Exception as exc:
                logger.warning("FacebookProvider search error for %r: %s", search_query, exc)
                continue

            for item in raw_results:
                if yielded >= max_results:
                    break

                url = item.get("href") or item.get("url") or ""
                parsed = urlparse(url)
                if "facebook.com" not in parsed.netloc.lower():
                    continue

                path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                if not path_parts:
                    continue

                page_slug = path_parts[0].lower().strip()
                if page_slug in _EXCLUDED_FB_PATHS:
                    continue

                if page_slug in seen_pages:
                    continue
                seen_pages.add(page_slug)

                title = (item.get("title") or "").strip()
                body = (item.get("body") or item.get("snippet") or "").strip()

                # Clean page name
                raw_title_lower = title.lower()
                if not title or "link to" in raw_title_lower or "facebook.com" in raw_title_lower:
                    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", page_slug)
                    clean_name = " ".join(words).title() if words else page_slug.replace(".", " ").replace("-", " ").title()
                else:
                    clean_name = re.sub(
                        r"\s*(\||-|·)\s*Facebook.*$",
                        "",
                        title,
                        flags=re.IGNORECASE,
                    ).strip()
                    clean_name = re.sub(
                        r"\s*(\||-|·)\s*(?:Karachi|Lahore|Islamabad|Rawalpindi|Home|About|Reviews|Posts|Services|Videos|Pakistan).*$",
                        "",
                        clean_name,
                        flags=re.IGNORECASE,
                    ).strip()
                    if "facebook" in clean_name.lower():
                        clean_name = re.split(r"facebook", clean_name, flags=re.IGNORECASE)[0].strip(" -|·")

                if not clean_name or len(clean_name) < 2 or clean_name.lower() in ("home", "about", "facebook"):
                    clean_name = page_slug.replace(".", " ").replace("-", " ").title()

                # Clean trailing Facebook numeric IDs (e.g. "Karachi Boutique 108024930873004" -> "Karachi Boutique")
                clean_name = re.sub(r"\s+\d{6,}$", "", clean_name).strip()

                # If name starts with a phone number (e.g. "030-987-254-98 Wholesale...")
                if re.match(r"^[\d\s\-\+\(\)]+", clean_name):
                    stripped_prefix = re.sub(r"^[\d\s\-\+\(\)]+(?:Wholesale|WhatsApp|Calling|Only|,|\.)*\s*", "", clean_name, flags=re.IGNORECASE).strip()
                    if len(stripped_prefix) >= 3:
                        clean_name = stripped_prefix
                    else:
                        words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", page_slug)
                        clean_name = " ".join(words).title() if words else page_slug.replace(".", " ").title()

                # Strict relevance check
                if query:
                    q_words = [w.lower() for w in re.split(r"\s+", query) if len(w) >= 3]
                    if q_words:
                        text_corpus = f"{clean_name} {page_slug} {body}".lower()
                        if not any(w in text_corpus for w in q_words):
                            continue

                # Extract followers / likes
                f_match = re.search(r"([\d\.,]+[KMkm]?)\s+(?:followers|likes)", body, re.IGNORECASE)
                followers = f_match.group(1) if f_match else None

                # Extract phones & WhatsApp from combined title and body
                combined_text = f"{title} {body}"
                formatted_phone = None
                whatsapp_url = None

                # 1. Scan for regional mobile numbers (UAE, Saudi, Pakistan, UK, etc.)
                clean_combined = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", combined_text, flags=re.IGNORECASE)

                # UAE mobile (050, 052, 054, 055, 056, 058) or +971 5x
                uae_cand = re.findall(r"(?:\+?971[\s\-\.]?0?|\b0)(5[024568])[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})\b", combined_text)
                if uae_cand:
                    fmt, wa = clean_phone_number(f"0{uae_cand[0][0]}{uae_cand[0][1]}{uae_cand[0][2]}", country="United Arab Emirates", city=city)
                    if fmt:
                        formatted_phone = fmt
                        whatsapp_url = wa

                # Pakistani mobile candidates (03xx / +923xx)
                if not formatted_phone:
                    pk_candidates = re.findall(r"(?:\+?92[\s\-\.]?|0)?3[\d\s\-\.]{8,14}\d", combined_text)
                    for cand in pk_candidates:
                        fmt, wa = clean_phone_number(cand, country="Pakistan", city=city)
                        if fmt:
                            formatted_phone = fmt
                            whatsapp_url = wa
                            break

                # Saudi mobile candidates (05x / +966 5x)
                if not formatted_phone:
                    sa_cand = re.findall(r"(?:\+?966[\s\-\.]?0?|\b0)(5\d)[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})\b", combined_text)
                    if sa_cand:
                        fmt, wa = clean_phone_number(f"0{sa_cand[0][0]}{sa_cand[0][1]}{sa_cand[0][2]}", country="Saudi Arabia", city=city)
                        if fmt:
                            formatted_phone = fmt
                            whatsapp_url = wa

                # Explicit labeled contact (WhatsApp: ..., Phone: ..., etc.)
                if not formatted_phone:
                    m_labeled = re.search(r"(?:whatsapp|wa|ph|call|phone|contact|order|📲|📞)[:\s]+(\+?[\d\s\-()]{7,20})", combined_text, re.IGNORECASE)
                    if m_labeled:
                        fmt, wa = clean_phone_number(m_labeled.group(1).strip(), country=country, city=city)
                        if fmt:
                            formatted_phone = fmt
                            whatsapp_url = wa

                # 2. General international phone fallback
                if not formatted_phone:
                    phone_raw_matches = re.findall(
                        r"(?:\+?\d{1,3}[\s\-]?)?(?:03\d{2}|3\d{2}|\d{3})[\s\-]?\d{3,4}[\s\-]?\d{2,4}",
                        combined_text,
                    )
                    for pr in phone_raw_matches:
                        fmt, wa = clean_phone_number(pr, country=country, city=city)
                        if fmt:
                            formatted_phone = fmt
                            whatsapp_url = wa
                            break

                # Extract email
                email = None
                email_matches = re.findall(
                    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", clean_combined
                )
                for em in email_matches:
                    em_low = em.lower().strip()
                    if not any(ign in em_low for ign in ("facebook.com", "fb.com", "sentry.io", "wixpress.com", "example.com", "cloudflare.com")):
                        email = em_low
                        break

                # Contact requirement: must have phone, email, or verified follower count
                if not formatted_phone and not email and not followers:
                    continue

                # Check for Instagram handle mention
                ig_from_fb = None
                m_ig = re.search(r"(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9\._\-]+)", combined_text)
                if m_ig and m_ig.group(1).lower() not in ("p", "reel", "explore", "stories", "share", "sharer"):
                    ig_from_fb = f"https://www.instagram.com/{m_ig.group(1)}/"

                # Check for website (strictly inspecting link aggregators & excluding social media)
                from app.engines.discovery.providers.instagram_provider import (
                    _EXCLUDED_DOMAINS as _SHARED_EXCLUDED,
                    _LINK_AGGREGATOR_DOMAINS as _SHARED_AGGREGATORS,
                    InstagramProvider,
                )
                urls_in_body = re.findall(
                    r'(?:https?://[^\s<>"]+|www\.[^\s<>"]+|[a-zA-Z0-9\-]+\.(?:com|pk|co|org|net|store|shop|online|ae|me|io|us|biz|nyc|ca)[^\s<>"]*)',
                    body,
                )
                website_url = None
                for cand in urls_in_body:
                    c = cand.strip(".,;:\"'()")
                    if not c.startswith("http"):
                        c = f"https://{c}"
                    try:
                        p = urlparse(c)
                        domain = p.netloc.lower() or p.path.split("/")[0].lower()
                        domain = re.sub(r"^www\.", "", domain)
                        if any(agg in domain for agg in _SHARED_AGGREGATORS):
                            found_site, found_wa = InstagramProvider._sync_inspect_aggregator(c)
                            if found_wa and not whatsapp_url:
                                whatsapp_url = f"https://wa.me/{found_wa.lstrip('+')}"
                            if found_site:
                                website_url = found_site
                                break
                            continue
                        if any(exc in domain for exc in _SHARED_EXCLUDED):
                            continue
                        if "." in domain and len(domain.split(".")[-1]) >= 2:
                            website_url = f"https://{domain}{p.path if p.path and p.path != '/' else ''}"
                            break
                    except Exception:
                        continue

                fb_url = f"https://www.facebook.com/{page_slug}/"
                has_web = bool(website_url)
                if not has_web:
                    pitch = (
                        f"Hello {clean_name}! Saw your Facebook business page. Noticed you don't "
                        f"have an active website linked — losing potential Google search customers. "
                        f"We build modern websites that rank on Google and convert visitors directly to your WhatsApp. "
                        f"Would you like to see a free design mockup?"
                    )
                else:
                    pitch = (
                        f"Hello {clean_name}! Saw your business page on Facebook. We help local businesses "
                        f"turn their web presence into more bookings and calls. Would you like a free quick audit?"
                    )

                raw_data = {
                    "page_slug": page_slug,
                    "facebook_url": fb_url,
                    "instagram_url": ig_from_fb,
                    "followers": followers,
                    "whatsapp_url": whatsapp_url,
                    "pitch": pitch,
                    "bio_snippet": body,
                    "has_website": has_web,
                    "source_provider": "facebook",
                }

                result = BusinessResult(
                    name=clean_name,
                    address=None,
                    city=city,
                    state=None,
                    country=country or ("Pakistan" if formatted_phone and formatted_phone.startswith("+92") else None),
                    phone=formatted_phone,
                    email=email,
                    website_url=website_url,
                    category=industry or "Local Business / Facebook Page",
                    source="facebook",
                    source_id=page_slug,
                    raw_data=raw_data,
                )

                yield result
                yielded += 1
                await asyncio.sleep(0.05)

    @staticmethod
    def _build_queries(
        query: str, country: Optional[str], city: Optional[str], industry: Optional[str]
    ) -> List[str]:
        target = query.strip() if query else (industry or "business services")
        loc = f'"{city}"' if city else (f'"{country}"' if country else "")

        target_loc = f"{city or ''} {country or ''}".lower()
        is_uae = any(c in target_loc for c in ("dubai", "abu dhabi", "sharjah", "ajman", "uae", "emirates"))
        is_saudi = any(c in target_loc for c in ("riyadh", "jeddah", "mecca", "medina", "dammam", "saudi", "ksa"))
        is_pk = any(
            c in target_loc
            for c in (
                "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
                "peshawar", "multan", "quetta", "sialkot", "gujranwala", "pakistan"
            )
        )
        is_uk = any(c in target_loc for c in ("london", "manchester", "birmingham", "leeds", "uk", "kingdom"))

        queries = [
            f'site:facebook.com "{target}" {loc}'.strip(),
            f'{target} {loc} facebook page "contact"'.strip(),
            f'{target} {loc} facebook page "whatsapp"'.strip(),
            f'{target} {loc} facebook page "@gmail.com"'.strip(),
        ]
        if is_uae:
            queries.insert(0, f'{target} {loc} "facebook.com" "050"'.strip())
            queries.insert(1, f'{target} {loc} "facebook.com" "WhatsApp" "05"'.strip())
        elif is_saudi:
            queries.insert(0, f'{target} {loc} "facebook.com" "05" "واتساب"'.strip())
            queries.insert(1, f'{target} {loc} "facebook.com" "WhatsApp"'.strip())
        elif is_pk:
            queries.insert(0, f'{target} {loc} "facebook.com" WhatsApp 03'.strip())
            queries.insert(1, f'{target} {loc} facebook page "0300"'.strip())
        elif is_uk:
            queries.insert(0, f'{target} {loc} "facebook.com" "07"'.strip())
            queries.insert(1, f'{target} {loc} facebook page "enquiries"'.strip())
        else:
            queries.insert(0, f'{target} {loc} facebook page "phone"'.strip())
            queries.insert(1, f'{target} {loc} "facebook.com" order'.strip())

        return [q for q in queries if q]

    async def _search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query, max_results)

    @staticmethod
    def _sync_search(query: str, max_results: int) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=min(max_results, 100)))
        except Exception as exc:
            logger.warning("ddgs search error for Facebook query %r: %s", query, exc)
            return []
