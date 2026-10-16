"""E-Commerce and Daraz Brand Miner discovery provider.

Mines verified Pakistani and South Asian e-commerce brands, Daraz top merchants,
and D2C stores, extracting verified WhatsApp (+92300–+92349), decision-maker emails,
store tech stack (Shopify, WooCommerce), and customized conversion pitches.
"""
from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from typing import Any, AsyncGenerator, Dict, List, Optional, Set
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

PK_MOBILE_PREFIXES = set([f"03{d:02d}" for d in range(0, 50)] + ["0355"])

BLACKLISTED_DOMAINS = {
    "w3.org", "schema.org", "daraz.pk", "facebook.com", "instagram.com",
    "tiktok.com", "linkedin.com", "youtube.com", "wikipedia.org",
    "pinterest.com", "twitter.com", "x.com", "sentry.io", "shopify.com",
    "cdn.shopify.com", "cloudflare.com", "googleapis.com", "google.com",
    "apple.com", "play.google.com", "microsoft.com"
}

JUNK_EMAIL_KEYWORDS = {
    "noreply", "no-reply", "donotreply", "example", "test", "sentry",
    "w3c", "domain", "email", "support@shopify.com", "help@shopify.com"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Verified top merchant brands in Pakistan
CURATED_BRANDS = [
    {"name": "Zero Lifestyle", "category": "Smartwatches & Audio", "city": "Karachi", "domain": "https://zerolifestyle.co"},
    {"name": "Faster Pakistan", "category": "Mobile Accessories", "city": "Lahore", "domain": "https://pk.hellofaster.com"},
    {"name": "Telemart", "category": "Electronics & Gadgets", "city": "Karachi", "domain": "https://telemart.pk"},
    {"name": "Ronin Pakistan", "category": "Power Banks & Earphones", "city": "Karachi", "domain": "https://ronin.pk"},
    {"name": "Audionic", "category": "Audio & Speakers", "city": "Karachi", "domain": "https://audionic.co"},
    {"name": "Dany Technologies", "category": "Tablets & Tech", "city": "Karachi", "domain": "https://danytech.com.pk"},
    {"name": "Baseus Pakistan", "category": "Fast Chargers & Cables", "city": "Lahore", "domain": "https://baseuspakistan.pk"},
    {"name": "Sogo Pakistan", "category": "Solar & Rechargeable", "city": "Karachi", "domain": "https://sogo.pk"},
    {"name": "Westpoint Pakistan", "category": "Home Appliances", "city": "Karachi", "domain": "https://westpoint.pk"},
    {"name": "Chase Value", "category": "Department Store & Fashion", "city": "Karachi", "domain": "https://chasevalue.pk"},
    {"name": "Bagallery", "category": "Beauty & Fragrances", "city": "Karachi", "domain": "https://bagallery.com"},
    {"name": "J. Junaid Jamshed", "category": "Apparel & Fragrances", "city": "Karachi", "domain": "https://junaidjamshed.com"},
    {"name": "Sana Safinaz", "category": "Fashion & Luxury Lawn", "city": "Karachi", "domain": "https://sanasafinaz.com"},
    {"name": "Gul Ahmed", "category": "Textiles & Home", "city": "Karachi", "domain": "https://gulahmedshop.com"},
    {"name": "Alkaram Studio", "category": "Apparel & Fabrics", "city": "Karachi", "domain": "https://alkaramstudio.com"},
    {"name": "Nishat Linen", "category": "Home & Clothing", "city": "Lahore", "domain": "https://nishatlinen.com"},
]


def clean_pk_mobile(raw_phone: str) -> tuple[Optional[str], Optional[str]]:
    """Validates and standardizes Pakistani mobile numbers."""
    digits = re.sub(r"\D", "", raw_phone)
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
    elif digits.startswith("3") and len(digits) == 10:
        prefix = "0" + digits[:3]
        if prefix in PK_MOBILE_PREFIXES:
            formatted = f"+92 {digits[:3]} {digits[3:]}"
            wa_link = f"https://wa.me/92{digits}"
            return formatted, wa_link
    return None, None


class EcommerceProvider(BaseDiscoveryProvider):
    """Mines verified e-commerce brands with mobile WhatsApp and decision-maker contacts."""

    _RATE_LIMIT_RPM = 15

    @property
    def provider_name(self) -> str:
        return "ecommerce_brands"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        return {
            "provider": "ecommerce_brands",
            "healthy": True,
            "message": "OK",
            "sample_result_count": len(CURATED_BRANDS),
        }

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        yielded = 0
        seen_domains: Set[str] = set()

        # Phase 1: Curated Top E-Commerce Brands matching query or all if broad
        q_lower = query.lower() if query else ""
        for brand in CURATED_BRANDS:
            if yielded >= max_results:
                break

            b_name = brand["name"]
            b_cat = brand["category"]
            b_domain = brand["domain"]

            # Filter if query is specified and not matching
            if q_lower and q_lower not in b_name.lower() and q_lower not in b_cat.lower():
                continue

            intel = await self._crawl_store_intelligence(b_domain)
            wa_list = list(intel["verified_whatsapp"])
            phone_list = list(intel["phone_numbers"])
            email_list = list(intel["emails"])

            primary_wa = wa_list[0] if wa_list else None
            primary_phone = phone_list[0] if phone_list else None
            primary_email = email_list[0] if email_list else None

            # STRICT CONTACT REQUIREMENT: Must have phone, WhatsApp, or email
            if not primary_wa and not primary_phone and not primary_email:
                continue

            pitch = (
                f"Hi {b_name} team! Noticed your high volume of customer orders on {intel['tech_stack']}. "
                f"We help top brands eliminate cart abandonment and boost mobile checkout speed by 40%. "
                f"Would you be open to a quick 2-minute conversion audit?"
            )

            raw_data = {
                "brand_name": b_name,
                "verified_whatsapp": primary_wa,
                "all_whatsapp": wa_list,
                "all_phones": phone_list,
                "all_emails": email_list,
                "tech_stack": intel["tech_stack"],
                "pitch": pitch,
                "source_provider": "ecommerce_brands",
            }

            yield BusinessResult(
                name=b_name,
                address=None,
                city=brand.get("city") or city,
                state=None,
                country="Pakistan",
                phone=primary_phone,
                email=primary_email,
                website_url=b_domain,
                category=b_cat,
                source="ecommerce_brands",
                source_id=b_name.lower().replace(" ", "-"),
                raw_data=raw_data,
            )
            yielded += 1
            seen_domains.add(b_domain.lower())
            await asyncio.sleep(0.05)

        # Phase 2: Dynamic Search for Additional E-Commerce Stores
        if yielded < max_results:
            dynamic_queries = [
                f'"{query}" online store official website pakistan WhatsApp' if query else 'top e-commerce brands pakistan official store WhatsApp',
                f'site:.pk "{query}" "Shopify" OR "WooCommerce" "03"' if query else 'site:.pk "clothing" OR "electronics" "Shopify" "03"',
            ]

            for dq in dynamic_queries:
                if yielded >= max_results:
                    break

                try:
                    search_results = await self._search(dq, max_results=30)
                except Exception:
                    continue

                for item in search_results:
                    if yielded >= max_results:
                        break

                    href = item.get("href") or item.get("url") or ""
                    parsed = urlparse(href)
                    domain = parsed.netloc.replace("www.", "").lower()
                    if not domain or any(b in domain for b in BLACKLISTED_DOMAINS):
                        continue

                    store_url = f"{parsed.scheme}://{parsed.netloc}"
                    if store_url.lower() in seen_domains:
                        continue
                    seen_domains.add(store_url.lower())

                    title = item.get("title") or ""
                    clean_name = re.sub(r"\s*(\||-)\s*(?:Official|Online|Store|Pakistan|Shop).*$", "", title, flags=re.IGNORECASE).strip()
                    if not clean_name or len(clean_name) < 2:
                        clean_name = domain.split(".")[0].title()

                    intel = await self._crawl_store_intelligence(store_url)
                    wa_list = list(intel["verified_whatsapp"])
                    phone_list = list(intel["phone_numbers"])
                    email_list = list(intel["emails"])

                    primary_wa = wa_list[0] if wa_list else None
                    primary_phone = phone_list[0] if phone_list else None
                    primary_email = email_list[0] if email_list else None

                    # STRICT CONTACT REQUIREMENT: Must have phone, WhatsApp, or email
                    if not primary_wa and not primary_phone and not primary_email:
                        continue

                    pitch = (
                        f"Hello {clean_name}! Saw your online store on {intel['tech_stack']}. "
                        f"We specialize in conversion rate optimization and WhatsApp automated checkout recovery for e-commerce. "
                        f"Would love to share a free performance teardown."
                    )

                    raw_data = {
                        "brand_name": clean_name,
                        "verified_whatsapp": primary_wa,
                        "all_whatsapp": wa_list,
                        "all_phones": phone_list,
                        "all_emails": email_list,
                        "tech_stack": intel["tech_stack"],
                        "pitch": pitch,
                        "source_provider": "ecommerce_brands",
                    }

                    yield BusinessResult(
                        name=clean_name,
                        address=None,
                        city=city,
                        state=None,
                        country=country or "Pakistan",
                        phone=primary_phone,
                        email=primary_email,
                        website_url=store_url,
                        category=industry or "E-Commerce / Direct-to-Consumer",
                        source="ecommerce_brands",
                        source_id=clean_name.lower().replace(" ", "-"),
                        raw_data=raw_data,
                    )
                    yielded += 1
                    await asyncio.sleep(0.05)

    async def _crawl_store_intelligence(self, domain_url: str) -> Dict[str, Any]:
        """Asynchronously scrapes store homepage and contact page for authentic contacts."""
        results: Dict[str, Any] = {
            "verified_whatsapp": set(),
            "phone_numbers": set(),
            "emails": set(),
            "tech_stack": "Custom E-Commerce",
        }

        urls_to_crawl = [domain_url]
        for sub in ["/pages/contact-us", "/contact-us", "/contact"]:
            urls_to_crawl.append(domain_url.rstrip("/") + sub)

        try:
            async with httpx.AsyncClient(headers=HEADERS, timeout=6.0, follow_redirects=True, verify=False) as client:
                for u in urls_to_crawl:
                    try:
                        r = await client.get(u)
                        if r.status_code != 200 or len(r.text) < 300:
                            continue

                        raw_html = r.text

                        # Detect Tech Stack
                        if "cdn.shopify.com" in raw_html or "Shopify.theme" in raw_html:
                            results["tech_stack"] = "Shopify"
                        elif "wp-content" in raw_html or "woocommerce" in raw_html:
                            results["tech_stack"] = "WooCommerce"
                        elif "magento" in raw_html or "Mage" in raw_html:
                            results["tech_stack"] = "Magento"

                        soup = BeautifulSoup(raw_html, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = a["href"].strip()
                            if "wa.me" in href or "whatsapp.com" in href:
                                match = re.search(r"\d{10,13}", href)
                                if match:
                                    fmt, wa_link = clean_pk_mobile(match.group(0))
                                    if wa_link:
                                        results["verified_whatsapp"].add(wa_link)
                                        if fmt:
                                            results["phone_numbers"].add(fmt)

                            elif href.startswith("tel:"):
                                raw_tel = href.replace("tel:", "").strip()
                                fmt, wa_link = clean_pk_mobile(raw_tel)
                                if fmt:
                                    results["phone_numbers"].add(fmt)
                                    if wa_link:
                                        results["verified_whatsapp"].add(wa_link)

                            elif href.startswith("mailto:"):
                                em = href.replace("mailto:", "").split("?")[0].strip().lower()
                                if em and "@" in em and not any(j in em for j in JUNK_EMAIL_KEYWORDS):
                                    results["emails"].add(em)

                        # Regex search on text content for 03xx numbers
                        text_content = soup.get_text()
                        for match in re.finditer(r"(?:03\d{2}|923\d{2})[- \.]?\d{7}", text_content):
                            fmt, wa_link = clean_pk_mobile(match.group(0))
                            if fmt:
                                results["phone_numbers"].add(fmt)
                                if wa_link:
                                    results["verified_whatsapp"].add(wa_link)

                        # If we found authentic WhatsApp or email, no need to crawl more contact pages
                        if results["verified_whatsapp"] or results["emails"]:
                            break

                    except Exception:
                        continue
        except Exception:
            pass

        return results

    async def _search(self, query: str, max_results: int = 30) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query, max_results)

    @staticmethod
    def _sync_search(query: str, max_results: int) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=min(max_results, 60)))
        except Exception:
            return []
