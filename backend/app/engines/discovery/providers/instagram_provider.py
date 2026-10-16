"""Instagram business and social commerce discovery provider.

Finds authentic business profiles, boutiques, local brands, and DM sellers
on Instagram that operate via WhatsApp and direct messages, identifying
businesses with NO website for high-converting web design & digital outreach.
"""
from __future__ import annotations

import asyncio
import html
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

PK_MOBILE_PREFIXES = set([f"03{d:02d}" for d in range(0, 50)] + ["0355"])

# Known non-business handles / system routes on Instagram
_EXCLUDED_IG_HANDLES = {
    "p", "reel", "reels", "stories", "explore", "about", "developer", "help",
    "directory", "legal", "privacy", "terms", "popular", "tags", "locations",
    "accounts", "direct", "tv", "reels_audio", "live", "login", "signup"
}

# Link aggregators and shorteners that often host or link to the business's actual webstore
_LINK_AGGREGATOR_DOMAINS = {
    "linktr.ee", "bio.link", "beacons.ai", "bit.ly", "tinyurl.com",
    "campsite.bio", "taplink.cc", "lnk.bio", "solo.to", "milkshake.app",
    "bento.me", "heylink.me", "snipfeed.co", "stan.store", "cutt.ly",
    "linkin.bio", "feedlink.io"
}

# Domains that must NEVER be treated as independent business websites
_EXCLUDED_DOMAINS = {
    # Social networks, streaming & messaging
    "instagram.com", "instagr.am", "cdninstagram.com", "fbcdn.net",
    "facebook.com", "fb.me", "fb.com", "m.me",
    "wa.me", "whatsapp.com", "api.whatsapp.com",
    "threads.net", "threads.com",
    "tiktok.com", "youtube.com", "youtu.be",
    "twitter.com", "x.com", "pinterest.com", "linkedin.com", "reddit.com",
    "snapchat.com", "soundcloud.com", "spotify.com", "apple.com", "music.apple.com",
    # Major search engines & platforms
    "google.com", "goo.gl", "microsoft.com", "yahoo.com", "bing.com",
    "wikipedia.org", "wikimedia.org", "github.com", "gitlab.com", "medium.com",
    "schema.org", "w3.org", "cloudflare.com", "gravatar.com",
    # Local directories & review aggregators
    "yelp.com", "tripadvisor.com", "mapquest.com", "yellowpages.com",
    "postcard.inc", "foursquare.com", "opentable.com", "resy.com",
    # Instagram mirror & viewer sites
    "picnob.com", "pixnoy.com", "picuki.com", "dumpor.com", "dumpoir.com",
    "imginn.com", "greatfon.com", "instanavigation.com", "anonigviewer.com",
    "mystalk.net", "storiesdown.com", "pixwox.com", "inflact.com",
    "greenpointers.com", "timeout.com", "eater.com", "infatuation.com",
}


def clean_phone_number(
    raw_phone: str,
    country: Optional[str] = None,
    city: Optional[str] = None,
    is_whatsapp: bool = False,
    is_pk: bool = False,
) -> tuple[Optional[str], Optional[str]]:
    """Clean and validate phone numbers across UAE, Saudi, Qatar, Kuwait, UK, PK, US, prioritizing E.164 and WhatsApp formatting."""
    if not raw_phone:
        return None, None
    digits = re.sub(r"\D", "", raw_phone)
    if not digits or len(digits) < 7:
        return None, None

    # Pakistani mobile: 923xxxxxxxxx (12 digits) or 03xxxxxxxxx (11 digits) or 3xxxxxxxxx (10 digits)
    if digits.startswith("923") and len(digits) == 12:
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
    elif digits.startswith("3") and len(digits) == 10 and (is_pk or (country and "pakistan" in country.lower())):
        prefix = "0" + digits[:3]
        if prefix in PK_MOBILE_PREFIXES:
            formatted = f"+92 {digits[:3]} {digits[3:]}"
            wa_link = f"https://wa.me/92{digits}"
            return formatted, wa_link

    # If this query is specifically for Pakistan and has a non-Pakistani prefix, reject
    if is_pk and not digits.startswith("92"):
        return None, None

    # Use PhoneValidator to validate and format across UAE, Saudi, UK, Qatar, Kuwait, US, etc.
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

    # Direct fallback for UAE: 05x or 9715x
    if (digits.startswith("9715") and len(digits) == 12) or (digits.startswith("05") and len(digits) == 10 and not is_pk):
        pure_971 = digits if digits.startswith("9715") else f"971{digits[1:]}"
        formatted = f"+971 {pure_971[3:5]} {pure_971[5:8]} {pure_971[8:]}"
        return formatted, f"https://wa.me/{pure_971}"

    # Direct fallback for Saudi Arabia: 05x or 9665x
    if digits.startswith("9665") and len(digits) == 12:
        formatted = f"+966 {digits[3:5]} {digits[5:8]} {digits[8:]}"
        return formatted, f"https://wa.me/{digits}"

    # Direct fallback for UK: 07x or 447x
    if digits.startswith("447") and 12 <= len(digits) <= 13:
        formatted = f"+44 {digits[2:6]} {digits[6:]}"
        return formatted, f"https://wa.me/{digits}"
    elif digits.startswith("07") and len(digits) == 11 and not is_pk:
        formatted = f"+44 {digits[1:5]} {digits[5:]}"
        return formatted, f"https://wa.me/44{digits[1:]}"

    # US / Canada standard
    if digits.startswith("1") and len(digits) == 11 and not is_pk:
        formatted = f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        wa_link = f"https://wa.me/{digits}"
        return formatted, wa_link
    elif len(digits) == 10 and not digits.startswith("0") and not is_pk:
        formatted = f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        wa_link = f"https://wa.me/1{digits}"
        return formatted, wa_link

    # International standard: 10 to 15 digits (if marked as WhatsApp or starts with country prefix)
    if 10 <= len(digits) <= 15 and is_whatsapp and not digits.startswith("0"):
        formatted = f"+{digits}"
        wa_link = f"https://wa.me/{digits}"
        return formatted, wa_link

    return None, None


class InstagramProvider(BaseDiscoveryProvider):
    """Discovers Instagram business profiles with verified WhatsApp and DM handles."""

    _RATE_LIMIT_RPM = 15

    @property
    def provider_name(self) -> str:
        return "instagram"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        try:
            results = await self._search("site:instagram.com clothing store", max_results=1)
            return {
                "provider": "instagram",
                "healthy": True,
                "message": "OK",
                "sample_result_count": len(results),
            }
        except Exception as exc:
            return {"provider": "instagram", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        import httpx

        is_pk = (country and "pakistan" in country.lower()) or (
            (city or "")
            and any(
                c in (city or "").lower()
                for c in (
                    "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
                    "peshawar", "multan", "quetta", "sialkot", "gujranwala", "pakistan"
                )
            )
        )

        queries = self._build_queries(query, country, city, industry)
        seen_handles: set[str] = set()
        yielded = 0
        per_query = min(25, max(12, (max_results * 2) // max(1, len(queries))))

        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
            "Accept-Language": "en-US,en;q=0.9",
        }

        async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
            for search_query in queries:
                if yielded >= max_results:
                    break

                try:
                    raw_results = await self._search(search_query, max_results=per_query)
                except Exception as exc:
                    logger.warning("InstagramProvider search error for %r: %s", search_query, exc)
                    continue

                for item in raw_results:
                    if yielded >= max_results:
                        break

                    url = item.get("href") or item.get("url") or ""
                    parsed = urlparse(url)
                    if "instagram.com" not in parsed.netloc.lower():
                        continue

                    title = (item.get("title") or "").strip()
                    body = (item.get("body") or item.get("snippet") or "").strip()
                    combined_text = f"{title} {body}"

                    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                    if not path_parts:
                        continue

                    candidate_handle: Optional[str] = None

                    # 1. Direct profile URL: https://instagram.com/<handle>/
                    if (
                        path_parts[0] not in _EXCLUDED_IG_HANDLES
                        and not path_parts[0].startswith(("p", "reel", "stories", "popular", "explore"))
                    ):
                        candidate_handle = path_parts[0].lower().split("?")[0].strip()

                    # 2. If shortcode (/p/ or /reel/), fetch post with Googlebot UA to resolve handle
                    if not candidate_handle and path_parts[0] in ("p", "reel"):
                        try:
                            p_resp = await client.get(url, timeout=3.5)
                            m_og_url = re.search(
                                r'<meta\s+property=\"og:url\"\s+content=\"https://www\.instagram\.com/([a-zA-Z0-9_\.]+)/',
                                p_resp.text,
                            )
                            if (
                                m_og_url
                                and m_og_url.group(1).lower() not in _EXCLUDED_IG_HANDLES
                                and m_og_url.group(1).lower() not in ("p", "reel")
                            ):
                                candidate_handle = m_og_url.group(1).lower().strip()

                            m_tw = re.search(
                                r'<meta\s+(?:name|property)=\"(?:twitter:title|og:title)\"\s+content=\"([^\"]+)\"',
                                p_resp.text,
                            )
                            if m_tw:
                                combined_text += " " + m_tw.group(1)
                                if not candidate_handle:
                                    m_tw_handle = re.search(r"(?:@|&#064;)([a-zA-Z0-9_\.]+)", m_tw.group(1))
                                    if m_tw_handle and m_tw_handle.group(1).lower() not in _EXCLUDED_IG_HANDLES:
                                        candidate_handle = m_tw_handle.group(1).lower().strip()
                        except Exception:
                            pass

                    # 3. Extract handle from snippet: "- <handle> on <date>:"
                    if not candidate_handle:
                        m_snip = re.search(r"-\s*([a-zA-Z0-9_\.]+)\s+on\s+[A-Za-z]+", body)
                        if (
                            m_snip
                            and m_snip.group(1).lower() not in _EXCLUDED_IG_HANDLES
                            and m_snip.group(1).lower() not in ("p", "reel")
                        ):
                            candidate_handle = m_snip.group(1).lower().strip()

                    # 4. Extract handle from title: (@<handle>) or <handle> on Instagram
                    if not candidate_handle:
                        m_title = re.search(r"\(@([a-zA-Z0-9_\.]+)\)", combined_text)
                        if (
                            m_title
                            and m_title.group(1).lower() not in _EXCLUDED_IG_HANDLES
                            and m_title.group(1).lower() not in ("p", "reel")
                        ):
                            candidate_handle = m_title.group(1).lower().strip()

                    if (
                        not candidate_handle
                        or len(candidate_handle) < 2
                        or candidate_handle in _EXCLUDED_IG_HANDLES
                        or candidate_handle in seen_handles
                    ):
                        continue
                    seen_handles.add(candidate_handle)

                    # ──────────────────────────────────────────────────────────
                    # Direct Profile Inspection with Googlebot User-Agent
                    # ──────────────────────────────────────────────────────────
                    profile_html = ""
                    try:
                        p_resp = await client.get(
                            f"https://www.instagram.com/{candidate_handle}/",
                            timeout=4.0,
                        )
                        if p_resp.status_code == 200:
                            profile_html = p_resp.text
                    except Exception as p_err:
                        logger.debug("Profile fetch error for @%s: %s", candidate_handle, p_err)

                    followers: Optional[str] = None
                    clean_name: Optional[str] = None
                    bio_text: str = ""

                    # Parse exact OpenGraph / Meta Description
                    desc_m = re.search(r'<meta\s+content=\"([^\"]+)\"\s+name=\"description\"', profile_html)
                    if not desc_m:
                        desc_m = re.search(r'<meta\s+name=\"description\"\s+content=\"([^\"]+)\"', profile_html)
                    if not desc_m:
                        desc_m = re.search(r'<meta\s+property=\"og:description\"\s+content=\"([^\"]+)\"', profile_html)

                    if desc_m:
                        raw_desc = html.unescape(desc_m.group(1))
                        # Match standard format: "121K Followers, 3,646 Following, 2,184 Posts - Breads Bakery™ (@breadsbakery) on Instagram: \"...\""
                        m_full = re.match(
                            r'^([\d\.,]+[KMkm]?\s+Followers)[^\-]*-\s*([^(@]+)\s*\(@([^\)]+)\)\s*on Instagram:\s*\"?(.*?)\"?$',
                            raw_desc,
                            re.DOTALL,
                        )
                        if m_full:
                            followers = m_full.group(1).strip()
                            clean_name = m_full.group(2).strip()
                            bio_text = m_full.group(4).strip().rstrip('"')
                        else:
                            f_m = re.search(r'([\d\.,]+[KMkm]?\s+Followers)', raw_desc, re.IGNORECASE)
                            if f_m:
                                followers = f_m.group(1).strip()
                            n_m = re.search(r'(?:from|-)\s+([^(@•|]+)\s*\(@', raw_desc)
                            if n_m:
                                clean_name = n_m.group(1).strip()
                            bio_text = raw_desc

                    # Clean business name from <title> tag if not already found
                    if not clean_name:
                        t_m = re.search(r"<title>([^<]+)</title>", profile_html)
                        if t_m:
                            t_clean = html.unescape(t_m.group(1))
                            nm = re.match(r"^([^(@•|]+)", t_clean)
                            if nm:
                                clean_name = nm.group(1).strip()

                    # Fallback to search snippet title
                    if not clean_name:
                        nm_snip = re.match(r"^([^(@•|]+)", title)
                        if nm_snip:
                            clean_name = nm_snip.group(1).strip()

                    # Sanitize business name
                    if clean_name:
                        clean_name = re.sub(r"\s*(\||-)\s*Instagram.*$", "", clean_name, flags=re.IGNORECASE).strip()
                    if (
                        not clean_name
                        or len(clean_name) < 2
                        or "link to" in clean_name.lower()
                        or "instagram" in clean_name.lower()
                    ):
                        clean_name = candidate_handle.replace("_", " ").replace(".", " ").title()

                    # Query relevance check (stemmed match)
                    if query:
                        q_words = [
                            w.lower()
                            for w in re.split(r"\s+", query)
                            if len(w) >= 3 and w.lower() not in ("and", "the", "for", "with", "near", "best", "shop", "store", "all")
                        ]
                        if q_words:
                            corpus = f"{clean_name} {candidate_handle} {bio_text} {combined_text}".lower()
                            matched = any(qw[:4] in corpus or qw in corpus for qw in q_words)
                            if not matched:
                                continue

                    # ──────────────────────────────────────────────────────────
                    # Authentic Contact Information Extraction (Bio + Snippet + HTML)
                    # ──────────────────────────────────────────────────────────
                    formatted_phone: Optional[str] = None
                    whatsapp_url: Optional[str] = None

                    # Comprehensive search corpus with de-obfuscation
                    search_corpus = f"{bio_text} {combined_text} {profile_html[:15000]}"
                    clean_corpus = re.sub(r"\s*\[at\]\s*|\s*\(at\)\s*", "@", search_corpus, flags=re.IGNORECASE)

                    # 1. Check for explicit wa.me link
                    m_wa = re.search(r"(?:https?://)?(?:www\.)?wa\.me/(\+?\d+)", search_corpus)
                    if m_wa:
                        wa_digits = m_wa.group(1)
                        p_fmt, p_wa = clean_phone_number(wa_digits, country=country, city=city, is_whatsapp=True, is_pk=is_pk)
                        if p_fmt:
                            formatted_phone = p_fmt
                            whatsapp_url = p_wa

                    # 2. Regional phone candidates across UAE, Saudi, Pakistan, UK, etc.
                    if not formatted_phone:
                        # UAE mobile (050, 052, 054, 055, 056, 058) or +971 5x
                        uae_matches = re.findall(r"(?:\+?971[\s\-\.]?0?|\b0)(5[024568])[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})\b", search_corpus)
                        if uae_matches and not is_pk:
                            p_fmt, p_wa = clean_phone_number(f"0{uae_matches[0][0]}{uae_matches[0][1]}{uae_matches[0][2]}", country="United Arab Emirates", city=city, is_whatsapp=True)
                            if p_fmt:
                                formatted_phone = p_fmt
                                whatsapp_url = p_wa

                    if not formatted_phone and is_pk:
                        pk_matches = re.findall(r"(?:\+?92[\s\-\.]?|0)?(3\d{2})[\s\-\.]?(\d{7})", search_corpus)
                        for prefix, rest in pk_matches:
                            full_03 = "0" + prefix
                            if full_03 in PK_MOBILE_PREFIXES:
                                formatted_phone = f"+92 {prefix} {rest}"
                                whatsapp_url = f"https://wa.me/92{prefix}{rest}"
                                break

                    if not formatted_phone and country and "saudi" in country.lower():
                        sa_matches = re.findall(r"(?:\+?966[\s\-\.]?0?|\b0)(5\d)[\s\-\.]?(\d{3})[\s\-\.]?(\d{4})\b", search_corpus)
                        if sa_matches:
                            p_fmt, p_wa = clean_phone_number(f"0{sa_matches[0][0]}{sa_matches[0][1]}{sa_matches[0][2]}", country="Saudi Arabia", city=city, is_whatsapp=True)
                            if p_fmt:
                                formatted_phone = p_fmt
                                whatsapp_url = p_wa

                    # 3. Explicit labeled contact (WhatsApp: ..., Contact: ..., 📲 ...)
                    if not formatted_phone:
                        m_labeled = re.search(
                            r"(?:whatsapp|wa|ph|call|phone|contact|order|orders|booking|📲|📞)[:\s]+(\+?[\d\s\-()]{7,20})",
                            search_corpus,
                            re.IGNORECASE,
                        )
                        if m_labeled:
                            cand_ph = m_labeled.group(1).strip()
                            fmt, wa = clean_phone_number(cand_ph, country=country, city=city, is_whatsapp=True, is_pk=is_pk)
                            if fmt:
                                formatted_phone = fmt
                                whatsapp_url = wa

                    # Extract email (bio first, then search corpus)
                    email: Optional[str] = None
                    for text_src in (bio_text, clean_corpus):
                        if email:
                            break
                        email_matches = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text_src)
                        for em in email_matches:
                            em_low = em.lower().strip()
                            if not any(ign in em_low for ign in ("instagram.com", "facebook.com", "fb.com", "sentry.io", "wixpress.com", "example.com", "cloudflare.com")):
                                email = em_low
                                break

                    # ──────────────────────────────────────────────────────────
                    # Social Media Handles (Facebook)
                    # ──────────────────────────────────────────────────────────
                    facebook_url: Optional[str] = None
                    m_fb = re.search(
                        r"(?:https?://)?(?:www\.)?(?:facebook\.com|fb\.me|fb\.com)/([a-zA-Z0-9\._\-]+)",
                        search_corpus,
                    )
                    if m_fb:
                        fb_slug = m_fb.group(1).lower()
                        if fb_slug not in ("sharer", "share", "tr", "home", "privacy", "help", "legal"):
                            facebook_url = f"https://www.facebook.com/{m_fb.group(1)}"

                    # ──────────────────────────────────────────────────────────
                    # Multi-Layer Website Detection & Verification
                    # ──────────────────────────────────────────────────────────
                    website_url, extra_wa, extra_email = await self._verify_website(
                        client=client,
                        handle=candidate_handle,
                        clean_name=clean_name,
                        bio_text=bio_text,
                        country=country,
                    )
                    if not formatted_phone and extra_wa:
                        formatted_phone, whatsapp_url = clean_phone_number(extra_wa, country=country, city=city, is_whatsapp=True, is_pk=is_pk)
                    if not email and extra_email:
                        email = extra_email

                    ig_url = f"https://www.instagram.com/{candidate_handle}/"
                    has_web = bool(website_url)

                    # Ultra-targeted high-converting outreach pitches
                    if not has_web:
                        ind_low = (industry or "").lower()
                        loc_display = city or country or "your city"
                        if "bakery" in ind_low or "cake" in ind_low or "food" in ind_low:
                            if formatted_phone or whatsapp_url:
                                pitch = (
                                    f"Hey {clean_name}! 🧁 Loved your bakery & cake creations on Instagram (@{candidate_handle}) in {loc_display}! "
                                    f"Noticed you take orders manually via WhatsApp/DM. We build beautiful online bakery menus with instant "
                                    f"WhatsApp order booking & flavor choices so customers can order 24/7. Can I share a quick 2-minute demo?"
                                )
                            else:
                                pitch = (
                                    f"Hey {clean_name}! 🧁 Loved your bakery & cake creations on Instagram (@{candidate_handle}) in {loc_display}! "
                                    f"Taking custom cake orders manually in DMs takes tons of time. We build automated online cake ordering "
                                    f"stores directly linked to your Instagram. Would you be open to a quick preview?"
                                )
                        elif "boutique" in ind_low or "cloth" in ind_low or "fashion" in ind_low or "dress" in ind_low:
                            if formatted_phone or whatsapp_url:
                                pitch = (
                                    f"Hey {clean_name}! 👗 Stunning fashion collection on Instagram (@{candidate_handle}) in {loc_display}! "
                                    f"Answering size, price & stock queries manually on WhatsApp takes up hours. We build fast, mobile-first "
                                    f"stores with 1-click WhatsApp order confirmation. Would you like a quick demo preview?"
                                )
                            else:
                                pitch = (
                                    f"Hey {clean_name}! 👗 Stunning fashion collection on Instagram (@{candidate_handle}) in {loc_display}! "
                                    f"Noticed you sell via DMs without an automated storefront yet. We build sleek mobile stores with "
                                    f"instant Instagram checkout so you never lose orders while offline. Open to a quick preview?"
                                )
                        elif "jewel" in ind_low or "access" in ind_low:
                            pitch = (
                                f"Hey {clean_name}! ✨ Beautiful jewellery catalog on Instagram (@{candidate_handle}) in {loc_display}! "
                                f"We design luxury online catalog stores with instant WhatsApp checkout to showcase prices & high-res designs. "
                                f"Would you be open to a quick 2-minute preview?"
                            )
                        elif "salon" in ind_low or "beauty" in ind_low:
                            pitch = (
                                f"Hey {clean_name}! ✂️ Loved your beauty work on Instagram (@{candidate_handle}) in {loc_display}! "
                                f"We build online booking portals linked to WhatsApp so clients can book appointments 24/7 without DM back-and-forth. "
                                f"Open to seeing a quick demo?"
                            )
                        else:
                            if formatted_phone or whatsapp_url:
                                pitch = (
                                    f"Hey {clean_name}! Loved your brand on Instagram (@{candidate_handle}) in {loc_display}. "
                                    f"Noticed you manage orders manually on WhatsApp and don't have an automated website yet. "
                                    f"We build custom high-converting web storefronts with direct WhatsApp checkout. Would you like a free quick preview?"
                                )
                            else:
                                pitch = (
                                    f"Hey {clean_name}! Loved your brand on Instagram (@{candidate_handle}) in {loc_display}. "
                                    f"Noticed you manage customer orders manually via Instagram DMs with no web store yet. "
                                    f"We build modern, mobile-first web storefronts that automate sales. Can I send a quick preview?"
                                )
                    else:
                        pitch = (
                            f"Hey {clean_name}! Saw your brand (@{candidate_handle}). We help growing e-commerce "
                            f"stores improve mobile loading speeds and double checkout conversions. "
                            f"Can I send you a quick 2-minute audit video?"
                        )

                    raw_data = {
                        "handle": f"@{candidate_handle}",
                        "instagram_url": ig_url,
                        "facebook_url": facebook_url,
                        "followers": followers,
                        "whatsapp_url": whatsapp_url,
                        "pitch": pitch,
                        "bio_snippet": bio_text if bio_text else f"Instagram store @{candidate_handle}",
                        "has_website": has_web,
                        "source_provider": "instagram",
                    }

                    result = BusinessResult(
                        name=clean_name,
                        address=None,
                        city=city,
                        state=None,
                        country=country or ("Pakistan" if is_pk else None),
                        phone=formatted_phone,
                        email=email,
                        website_url=website_url,
                        category=industry or "Social Commerce / Instagram Store",
                        source="instagram",
                        source_id=candidate_handle,
                        raw_data=raw_data,
                    )

                    yield result
                    yielded += 1
                    await asyncio.sleep(0.05)

    @staticmethod
    def _build_queries(
        query: str, country: Optional[str], city: Optional[str], industry: Optional[str]
    ) -> List[str]:
        target = query.strip() if query else (industry or "boutique")
        # Strip any extraneous non-alphanumeric symbols except & / , -
        target = re.sub(r"[^\w\s&/,-]", "", target).strip()
        target_clean = target
        loc_from_query = None

        m_in = re.search(r"^(.*?)\s+in\s+([A-Za-z\s,]+)$", target, re.IGNORECASE)
        if m_in:
            target_clean = m_in.group(1).strip()
            loc_from_query = m_in.group(2).strip()

        loc = f'"{city}"' if city else (f'"{loc_from_query}"' if loc_from_query else (f'"{country}"' if country else ""))

        def stem_term(t: str) -> str:
            parts = t.split()
            stemmed_parts = []
            for p in parts:
                p_low = p.lower()
                if p_low.endswith("ies") and len(p_low) > 4:
                    stemmed_parts.append(p[:-3] + "y")
                elif any(p_low.endswith(suf) for suf in ("sses", "shes", "ches", "xes", "zes")):
                    stemmed_parts.append(p[:-2])
                elif p_low.endswith("s") and not p_low.endswith("ss") and len(p_low) > 3:
                    stemmed_parts.append(p[:-1])
                else:
                    stemmed_parts.append(p)
            return " ".join(stemmed_parts)

        # Split compound niches like "Bakeries & Custom Cakes" or "Clothing & Boutiques"
        sub_terms = [t.strip() for t in re.split(r"[\&/,]|(?:\band\b)", target_clean, flags=re.IGNORECASE) if t.strip()]
        if not sub_terms:
            sub_terms = [target_clean]

        keywords: List[str] = []
        for st in sub_terms:
            stemmed = stem_term(st)
            if stemmed not in keywords:
                keywords.append(stemmed)
            if st != stemmed and st not in keywords:
                keywords.append(st)

        target_loc = f"{city or ''} {loc_from_query or ''}".lower()
        is_uae = (country and any(u in country.lower() for u in ("uae", "emirates"))) or any(c in target_loc for c in ("dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "fujairah", "al ain"))
        is_saudi = (country and "saudi" in country.lower()) or any(c in target_loc for c in ("riyadh", "jeddah", "mecca", "medina", "dammam", "khobar", "tabuk"))
        is_qatar = (country and "qatar" in country.lower()) or any(c in target_loc for c in ("doha", "al rayyan"))
        is_kuwait = (country and "kuwait" in country.lower()) or any(c in target_loc for c in ("kuwait", "salmiya", "hawally"))
        is_pk = (country and "pakistan" in country.lower()) or any(
            c in target_loc
            for c in (
                "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad",
                "peshawar", "multan", "quetta", "sialkot", "gujranwala", "pakistan"
            )
        )
        is_uk = (country and any(u in country.lower() for u in ("kingdom", "uk", "britain", "england"))) or any(c in target_loc for c in ("london", "manchester", "birmingham", "leeds", "glasgow", "liverpool", "edinburgh"))
        is_us = (country and any(u in country.lower() for u in ("united states", "usa", "us"))) or any(c in target_loc for c in ("new york", "los angeles", "chicago", "houston", "miami", "dallas", "seattle", "austin", "san francisco"))

        queries: List[str] = []
        for kw in keywords:
            if is_uae:
                queries.append(f'site:instagram.com "{kw}" {loc} "050" "DM"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "055" "WhatsApp"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "wa.me/971"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order" "WhatsApp"'.strip())
            elif is_saudi:
                queries.append(f'site:instagram.com "{kw}" {loc} "05" "واتساب"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "05" "للطلب"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "wa.me/966"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "خاص" "واتساب"'.strip())
            elif is_qatar:
                queries.append(f'site:instagram.com "{kw}" {loc} "WhatsApp" "wa.me/974"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order"'.strip())
            elif is_kuwait:
                queries.append(f'site:instagram.com "{kw}" {loc} "WhatsApp" "wa.me/965"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order"'.strip())
            elif is_pk:
                queries.append(f'site:instagram.com "{kw}" {loc} "03" "DM"'.strip())
                queries.append(f'site:instagram.com {kw} {loc} "WhatsApp" "03"'.strip())
                queries.append(f'site:instagram.com {kw} {loc} "Cash on delivery"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "wa.me/92"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
            elif is_uk:
                queries.append(f'site:instagram.com "{kw}" {loc} "07" "DM to order"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "WhatsApp" "enquiries"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order"'.strip())
            elif is_us:
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order" "text"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "DM for orders" "@gmail.com"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order"'.strip())
            else:
                queries.append(f'site:instagram.com "{kw}" {loc} "DM to order"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "WhatsApp"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "wa.me/"'.strip())
                queries.append(f'site:instagram.com "{kw}" {loc} "@gmail.com"'.strip())
                queries.append(f'site:instagram.com {kw} {loc} "DM for orders"'.strip())
                queries.append(f'site:instagram.com {kw} {loc}'.strip())

        queries.append(f'site:instagram.com {target_clean} {loc}'.strip())

        seen_q = set()
        deduped = []
        for q in queries:
            if q and q not in seen_q:
                seen_q.add(q)
                deduped.append(q)
        return deduped


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
            logger.warning("ddgs search error for query %r: %s", query, exc)
            return []

    async def _verify_website(
        self,
        client: httpx.AsyncClient,
        handle: str,
        clean_name: str,
        bio_text: str,
        country: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Rigorously detects whether the Instagram business already has an external website.
        Returns (verified_website_url, verified_whatsapp_phone, verified_email).
        """
        clean_h = re.sub(r"[^a-zA-Z0-9]", "", handle.lower())
        extra_wa_from_agg: Optional[str] = None
        extra_email_from_agg: Optional[str] = None
        loop = asyncio.get_event_loop()

        # 1. Check bio_text for external domains/URLs
        urls_in_bio = re.findall(
            r'(?:https?://[^\s<>"]+|www\.[^\s<>"]+|[a-zA-Z0-9\-]+\.(?:com|pk|co|org|net|store|shop|online|ae|me|io|us|biz|nyc|ca)[^\s<>"]*)',
            bio_text,
            re.IGNORECASE,
        )
        for cand in urls_in_bio:
            cand_clean = cand.strip(".,;:\"'()")
            if not cand_clean.startswith("http"):
                cand_clean = f"https://{cand_clean}"
            try:
                p = urlparse(cand_clean)
                domain = p.netloc.lower() or p.path.split("/")[0].lower()
                domain = re.sub(r"^www\.", "", domain)

                # Check if it's a known link aggregator / shortener (Linktree, Beacons, Taplink, bit.ly)
                if any(agg in domain for agg in _LINK_AGGREGATOR_DOMAINS):
                    found_site, found_wa, found_em = await loop.run_in_executor(
                        None, self._sync_inspect_aggregator, cand_clean
                    )
                    if found_wa and not extra_wa_from_agg:
                        extra_wa_from_agg = found_wa
                    if found_em and not extra_email_from_agg:
                        extra_email_from_agg = found_em
                    if found_site:
                        return found_site, extra_wa_from_agg, extra_email_from_agg
                    continue

                if any(exc in domain for exc in _EXCLUDED_DOMAINS):
                    continue

                # The business owner placed this link in their own Instagram bio -> IT IS THEIR WEBSITE!
                if "." in domain and len(domain.split(".")[-1]) >= 2:
                    return f"https://{domain}{p.path if p.path and p.path != '/' else ''}", extra_wa_from_agg, extra_email_from_agg
            except Exception:
                continue

        # 2. Direct HTTP probe on standard domain patterns (e.g. {clean_h}.com, {clean_h}.pk, {clean_h}.ae)
        probe_urls = [
            f"https://www.{clean_h}.com",
            f"https://{clean_h}.com",
            f"https://www.{clean_h}.store",
            f"https://{clean_h}.shop",
        ]
        if country and "pakistan" in country.lower():
            probe_urls.extend([f"https://www.{clean_h}.pk", f"https://{clean_h}.pk"])
        elif country and any(u in country.lower() for u in ("uae", "emirates")):
            probe_urls.extend([f"https://www.{clean_h}.ae", f"https://{clean_h}.ae"])
        elif country and "saudi" in country.lower():
            probe_urls.extend([f"https://www.{clean_h}.sa", f"https://{clean_h}.sa"])

        for u in probe_urls:
            try:
                r = await client.get(u, timeout=2.0)
                if r.status_code < 400:
                    d = urlparse(str(r.url)).netloc.lower()
                    d = re.sub(r"^www\.", "", d)
                    if not any(exc in d for exc in _EXCLUDED_DOMAINS) and not any(agg in d for agg in _LINK_AGGREGATOR_DOMAINS):
                        return str(r.url), extra_wa_from_agg, extra_email_from_agg
            except Exception:
                pass

        # 3. Targeted open web query for official website
        found_from_search = await loop.run_in_executor(
            None, self._sync_resolve_external_website, handle, clean_name
        )
        if found_from_search:
            return found_from_search, extra_wa_from_agg, extra_email_from_agg

        return None, extra_wa_from_agg, extra_email_from_agg

    @staticmethod
    def _sync_inspect_aggregator(agg_url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
        import urllib.request
        from urllib.parse import urlparse

        req = urllib.request.Request(
            agg_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                final_url = resp.geturl()
                html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return None, None, None

        # Check if shortened URL redirected directly to an external website
        p_final = urlparse(final_url)
        d_final = p_final.netloc.lower().replace("www.", "")
        if (
            not any(exc in d_final for exc in _EXCLUDED_DOMAINS)
            and not any(agg in d_final for agg in _LINK_AGGREGATOR_DOMAINS)
            and "." in d_final
            and len(d_final.split(".")[-1]) >= 2
        ):
            return f"https://{d_final}", None, None

        # Extract WhatsApp if present on the page
        wa_match = re.search(r'(?:wa\.me/|api\.whatsapp\.com/send\?phone=)([0-9+]+)', html)
        wa_phone = wa_match.group(1) if wa_match else None
        if not wa_phone:
            tel_match = re.search(r'href=["\']tel:(\+?[0-9\s\-()]{7,20})["\']', html, re.IGNORECASE)
            if tel_match:
                wa_phone = tel_match.group(1)

        # Extract email from aggregator HTML (mailto: or clean regex)
        found_email: Optional[str] = None
        m_mailto = re.search(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html, re.IGNORECASE)
        if m_mailto:
            e = m_mailto.group(1).lower().strip()
            if not any(ign in e for ign in ("linktree", "beacons", "taplink", "sentry", "wixpress", "example", "cloudflare")):
                found_email = e
        if not found_email:
            raw_emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html)
            for re_e in raw_emails:
                re_low = re_e.lower().strip()
                if not any(ign in re_low for ign in ("linktr.ee", "beacons.ai", "taplink.cc", "sentry.io", "wixpress.com", "example.com", "cloudflare.com")):
                    found_email = re_low
                    break

        # Search for external website links inside the aggregator HTML
        raw_urls = re.findall(r'https?://[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/[^\s\"\'<>]*)?', html)
        for u in raw_urls:
            p = urlparse(u)
            d = p.netloc.lower().replace("www.", "")
            if (
                not any(exc in d for exc in _EXCLUDED_DOMAINS)
                and not any(agg in d for agg in _LINK_AGGREGATOR_DOMAINS)
                and "." in d
                and len(d.split(".")[-1]) >= 2
                and not any(cdn in d for cdn in ("gstatic.com", "googleapis.com", "consentjs", "sndcdn.com", "linksynergy.com", "datagrail.io", "gravatar.com", "w3.org", "schema.org", "unpkg.com", "jsdelivr.net"))
            ):
                return f"https://{d}", wa_phone, found_email

        return None, wa_phone, found_email

    async def _resolve_external_website(self, handle: str, clean_name: str) -> Optional[str]:
        """Resolves external website when linked via Instagram's 'Link in Bio' button."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_resolve_external_website, handle, clean_name)

    @staticmethod
    def _sync_resolve_external_website(handle: str, clean_name: str) -> Optional[str]:
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                results = list(ddgs.text(f'"{handle}"', max_results=6))
                for r in results:
                    href = r.get("href") or ""
                    p = urlparse(href)
                    domain = p.netloc.lower() or p.path.split("/")[0].lower()
                    domain = re.sub(r"^www\.", "", domain)
                    if any(exc in domain for exc in _EXCLUDED_DOMAINS):
                        continue
                    if "." in domain and len(domain.split(".")[-1]) >= 2:
                        if InstagramProvider._is_domain_relevant(domain, handle, clean_name):
                            return f"https://{domain}"

                for r in results:
                    snippet = f"{r.get('title', '')} {r.get('body', '')}"
                    candidates = re.findall(
                        r"(?:https?://)?(?:www\.)?([a-zA-Z0-9\-]+\.(?:com|org|net|nyc|store|shop|co|us|biz|io|pk))",
                        snippet,
                        re.IGNORECASE,
                    )
                    for cand in candidates:
                        d = cand.lower()
                        if not any(exc in d for exc in _EXCLUDED_DOMAINS) and "." in d and len(d.split(".")[-1]) >= 2:
                            if InstagramProvider._is_domain_relevant(d, handle, clean_name):
                                return f"https://{d}"
        except Exception as exc:
            logger.debug("Failed to resolve external website for @%s: %s", handle, exc)
        return None

    @staticmethod
    def _is_domain_relevant(domain: str, handle: str, clean_name: str) -> bool:
        """Verifies that an external domain matches the brand or Instagram handle."""
        h_clean = handle.lower().replace("_", "").replace(".", "")
        d_clean = domain.lower().replace("-", "").replace(".", "")
        d_root = domain.lower().split(".")[0].replace("-", "")
        n_clean = clean_name.lower().replace(" ", "").replace("-", "") if clean_name else ""

        if h_clean in d_clean or d_clean in h_clean:
            return True
        if d_root in h_clean or h_clean in d_root:
            return True
        if n_clean and (n_clean in d_clean or d_root in n_clean):
            return True
        return False
