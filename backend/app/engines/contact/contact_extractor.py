from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ─── Patterns ────────────────────────────────────────────────────────────────

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Only match numbers with explicit + country code
PHONE_PATTERN = re.compile(
    r"\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}"
)

# href="tel:+923001234567" — high confidence
TEL_HREF_PATTERN = re.compile(r'href=["\']tel:(\+[\d\s\-().]{7,25})["\']')

# href="mailto:someone@example.com" — high confidence
MAILTO_HREF_PATTERN = re.compile(r'href=["\']mailto:([^"\'?\s]+)["\']')

SOCIAL_PATTERNS = {
    "linkedin": re.compile(r"https?://(?:www\.)?linkedin\.com/(?:in|company)/[a-zA-Z0-9\-_%]+/?"),
    "facebook": re.compile(r"https?://(?:www\.)?facebook\.com/[a-zA-Z0-9.\-]+/?"),
    "twitter": re.compile(r"https?://(?:www\.)?(?:twitter|x)\.com/[a-zA-Z0-9_]+/?"),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/[a-zA-Z0-9_.]+/?"),
}

NAME_TITLE_PATTERNS = [
    re.compile(r"(?:CEO|CTO|CFO|COO|Owner|Founder|Director|Manager|President)\s*[:\-–]?\s*([A-Z][a-z]+ [A-Z][a-z]+)"),
    re.compile(r"([A-Z][a-z]+ [A-Z][a-z]+)\s*[,\-–]\s*(?:CEO|CTO|CFO|COO|Owner|Founder|Director|Manager|President)"),
]

# Section selectors — regex tries to isolate footer/contact sections before scanning
_CONTACT_SECTION_PATTERN = re.compile(
    r'(?:<(?:footer|section|div)[^>]*(?:id|class)=["\'][^"\']*(?:contact|footer|reach|address|get.in.touch)[^"\']*["\'][^>]*>)'
    r'(.*?)'
    r'(?:</(?:footer|section|div)>)',
    re.IGNORECASE | re.DOTALL,
)

ROLE_KEYWORDS = {
    "owner": ["owner", "founder", "proprietor", "principal"],
    "manager": ["manager", "gm", "general manager", "managing director"],
    "marketing": ["marketing", "digital", "social media", "content", "seo", "brand"],
    "technical": ["developer", "engineer", "it", "tech", "cto", "webmaster"],
    "sales": ["sales", "business development", "bd", "account"],
}

# Hard-reject only genuine junk — info@/admin@/support@ are kept, tagged low priority
JUNK_EMAIL_LOCAL = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "example", "test", "postmaster", "mailer-daemon",
}
# Kept for backward-compat import in other modules
EXCLUDED_EMAILS = JUNK_EMAIL_LOCAL


@dataclass
class ExtractedContact:
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    role: str = "unknown"
    source: str = "website"          # website | llm_inferred
    linkedin_url: Optional[str] = None
    confidence_score: float = 0.0
    email_confidence: str = "medium"  # high | medium | low
    phone_confidence: str = "medium"
    email_priority: str = "normal"    # normal | low (for info@, admin@, …)
    social_profiles: dict = field(default_factory=dict)


class ContactExtractor:
    def extract_from_html(self, html: str, url: str) -> list[ExtractedContact]:
        contacts: list[ExtractedContact] = []

        # Extract emails/phones with confidence levels
        href_emails = self._extract_mailto_hrefs(html)        # high confidence
        href_phones = self._extract_tel_hrefs(html)           # high confidence
        section_emails = self._extract_emails_from_sections(html)  # medium
        section_phones = self._extract_phones_from_sections(html)  # medium

        # Merge: high-confidence first, deduplicated
        all_emails: list[tuple[str, str]] = []  # (email, confidence)
        seen_e: set[str] = set()
        for e in href_emails:
            if e not in seen_e:
                all_emails.append((e, "high"))
                seen_e.add(e)
        for e in section_emails:
            if e not in seen_e:
                all_emails.append((e, "medium"))
                seen_e.add(e)

        all_phones: list[tuple[str, str]] = []  # (phone, confidence)
        seen_p: set[str] = set()
        for p in href_phones:
            if p not in seen_p:
                all_phones.append((p, "high"))
                seen_p.add(p)
        for p in section_phones:
            if p not in seen_p:
                all_phones.append((p, "medium"))
                seen_p.add(p)

        social = self._extract_social_profiles(html)
        names_with_titles = self._extract_names_and_titles(html)

        for email, email_conf in all_emails:
            local_part = email.split("@")[0].lower()
            if local_part in JUNK_EMAIL_LOCAL:
                continue
            email_priority = "low" if local_part in {
                "info", "contact", "hello", "support", "admin",
                "sales", "marketing", "webmaster", "team", "office",
            } else "normal"

            contact = ExtractedContact(
                email=email,
                source="website",
                social_profiles=social,
                email_confidence=email_conf,
                email_priority=email_priority,
            )
            if all_phones:
                contact.phone = all_phones[0][0]
                contact.phone_confidence = all_phones[0][1]

            if local_part not in JUNK_EMAIL_LOCAL:
                name = self._guess_name_from_email(local_part)
                if name:
                    contact.first_name = name[0]
                    contact.last_name = name[1] if len(name) > 1 else None
                    contact.full_name = " ".join(name)

            for name_info in names_with_titles:
                if name_info.get("name"):
                    contact.full_name = name_info["name"]
                    parts = name_info["name"].split()
                    contact.first_name = parts[0]
                    contact.last_name = parts[-1] if len(parts) > 1 else None
                if name_info.get("title"):
                    contact.title = name_info["title"]
                    contact.role = self._infer_role(name_info["title"])
                break

            if social.get("linkedin"):
                contact.linkedin_url = social["linkedin"]
            contact.confidence_score = self._calculate_confidence(contact)
            contacts.append(contact)

        # No email found — create phone-only contact if we have a phone
        if not contacts and all_phones:
            p, p_conf = all_phones[0]
            contact = ExtractedContact(
                phone=p,
                social_profiles=social,
                source="website",
                phone_confidence=p_conf,
            )
            if social.get("linkedin"):
                contact.linkedin_url = social["linkedin"]
            contact.confidence_score = 0.2
            contacts.append(contact)

        return contacts

    def generate_email_patterns(self, first_name: str, last_name: str, domain: str) -> list[dict[str, Any]]:
        patterns = []
        fn = first_name.lower()
        ln = last_name.lower()
        fi = fn[0] if fn else ""
        li = ln[0] if ln else ""

        candidates = [
            (f"{fn}.{ln}@{domain}", 0.85),
            (f"{fn}{ln}@{domain}", 0.75),
            (f"{fi}{ln}@{domain}", 0.70),
            (f"{fn}@{domain}", 0.60),
            (f"{fn}_{ln}@{domain}", 0.65),
            (f"{fi}.{ln}@{domain}", 0.70),
            (f"{ln}.{fn}@{domain}", 0.50),
            (f"{ln}{fi}@{domain}", 0.45),
        ]
        for email, confidence in candidates:
            patterns.append({"email": email, "confidence": confidence})
        return patterns

    # ── High-confidence href extraction ──────────────────────────────────

    @staticmethod
    def _extract_mailto_hrefs(html: str) -> list[str]:
        """Extract emails from mailto: href attributes — high confidence."""
        found = MAILTO_HREF_PATTERN.findall(html)
        seen: set[str] = set()
        unique: list[str] = []
        for email in found:
            lower = email.strip().lower()
            if "@" in lower and lower not in seen:
                seen.add(lower)
                unique.append(lower)
        return unique

    @staticmethod
    def _extract_tel_hrefs(html: str) -> list[str]:
        """Extract phones from tel: href attributes — high confidence."""
        found = TEL_HREF_PATTERN.findall(html)
        seen: set[str] = set()
        unique: list[str] = []
        for phone in found:
            normalized = re.sub(r"[^\d+]", "", phone)
            if normalized.startswith("+") and len(normalized) >= 8 and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    # ── Medium-confidence section-scoped extraction ───────────────────────

    @staticmethod
    def _get_contact_sections(html: str) -> str:
        """Extract footer/contact sections; fall back to full HTML."""
        sections = _CONTACT_SECTION_PATTERN.findall(html)
        return " ".join(sections) if sections else html

    def _extract_emails_from_sections(self, html: str) -> list[str]:
        """Regex email extraction scoped to contact/footer sections — medium confidence."""
        text = self._get_contact_sections(html)
        found = EMAIL_PATTERN.findall(text)
        seen: set[str] = set()
        unique: list[str] = []
        _asset_ext = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".woff")
        for email in found:
            lower = email.lower()
            if lower not in seen and not any(lower.endswith(ext) for ext in _asset_ext):
                seen.add(lower)
                unique.append(lower)
        return unique

    def _extract_phones_from_sections(self, html: str) -> list[str]:
        """Regex phone extraction scoped to contact/footer sections — medium confidence."""
        text = self._get_contact_sections(html)
        seen: set[str] = set()
        unique: list[str] = []
        for phone in PHONE_PATTERN.findall(text):
            normalized = re.sub(r"[^\d+]", "", phone)
            if normalized.startswith("+") and len(normalized) >= 8 and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def _extract_social_profiles(self, html: str) -> dict[str, str]:
        profiles = {}
        for platform, pattern in SOCIAL_PATTERNS.items():
            match = pattern.search(html)
            if match:
                profiles[platform] = match.group(0)
        return profiles

    def _extract_names_and_titles(self, html: str) -> list[dict[str, Optional[str]]]:
        results = []
        for pattern in NAME_TITLE_PATTERNS:
            for match in pattern.finditer(html):
                name = match.group(1).strip()
                title_match = re.search(
                    r"(CEO|CTO|CFO|COO|Owner|Founder|Director|Manager|President)",
                    match.group(0),
                )
                results.append({
                    "name": name,
                    "title": title_match.group(1) if title_match else None,
                })
        return results

    def _guess_name_from_email(self, local_part: str) -> Optional[list[str]]:
        for sep in [".", "_", "-"]:
            if sep in local_part:
                parts = local_part.split(sep)
                if len(parts) == 2 and all(p.isalpha() and len(p) > 1 for p in parts):
                    return [p.capitalize() for p in parts]
        return None

    def _infer_role(self, title: str) -> str:
        title_lower = title.lower()
        for role, keywords in ROLE_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                return role
        return "general"

    def _calculate_confidence(self, contact: ExtractedContact) -> float:
        score = 0.0
        if contact.email:
            score += 0.4
            local = contact.email.split("@")[0].lower()
            if local not in EXCLUDED_EMAILS:
                score += 0.1
        if contact.full_name:
            score += 0.2
        if contact.phone:
            score += 0.15
        if contact.title:
            score += 0.1
        if contact.linkedin_url:
            score += 0.15
        return min(score, 1.0)
