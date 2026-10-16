"""
Contact validation module.

EmailValidator  — MX lookup via dnspython (SMTP RCPT off by default).
PhoneValidator  — E.164 formatting + number-type detection via phonenumbers.
                  MOBILE and FIXED_LINE_OR_MOBILE → whatsapp_eligible=True.
                  Pure FIXED_LINE / UNKNOWN → whatsapp_eligible=False.

Confidence levels
-----------------
high   — parsed from mailto:/tel: href
medium — regex from contact/footer section
low    — LLM-inferred (must pass validation before saving)
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ─── Confidence ──────────────────────────────────────────────────────────────

class Confidence(str, Enum):
    HIGH   = "high"    # href-sourced
    MEDIUM = "medium"  # regex from contact section
    LOW    = "low"     # LLM-inferred


# ─── Email validation ─────────────────────────────────────────────────────────

class EmailStatus(str, Enum):
    VALID        = "valid"        # MX record exists
    INVALID      = "invalid"      # definitive failure (no MX, junk domain)
    UNVERIFIABLE = "unverifiable" # DNS timeout or other transient error


@dataclass
class EmailValidationResult:
    email: str
    status: EmailStatus
    confidence: Confidence = Confidence.MEDIUM
    priority: str = "normal"   # "low" for generic addresses (info@, support@, …)
    mx_hosts: list = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_usable(self) -> bool:
        """True for valid or unverifiable (give benefit of the doubt)."""
        return self.status in (EmailStatus.VALID, EmailStatus.UNVERIFIABLE)


# Addresses that are kept but flagged as low-priority (not rejected)
_LOW_PRIORITY_LOCAL = {
    "info", "contact", "hello", "support", "admin",
    "sales", "marketing", "webmaster", "team", "office",
}

# Addresses that are ALWAYS rejected
_JUNK_LOCAL = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "example", "test", "postmaster", "mailer-daemon",
}

_JUNK_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "mailinator.com"}

# Common image/asset false positives from regex on HTML
_ASSET_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js", ".woff")


class EmailValidator:
    """Validates email addresses using MX record lookup."""

    def __init__(self, smtp_rcpt: bool = False) -> None:
        # smtp_rcpt is intentionally off by default — can get sender IP flagged
        self._smtp_rcpt = smtp_rcpt

    def validate(self, email: str, confidence: Confidence = Confidence.MEDIUM) -> EmailValidationResult:
        email = email.strip().lower()

        # Reject obvious asset false positives
        if any(email.endswith(ext) for ext in _ASSET_EXTENSIONS):
            return EmailValidationResult(
                email=email, status=EmailStatus.INVALID,
                confidence=confidence, error="asset_false_positive",
            )

        if "@" not in email:
            return EmailValidationResult(
                email=email, status=EmailStatus.INVALID,
                confidence=confidence, error="no_at_symbol",
            )

        local, _, domain = email.rpartition("@")

        if domain in _JUNK_DOMAINS:
            return EmailValidationResult(
                email=email, status=EmailStatus.INVALID,
                confidence=confidence, error="junk_domain",
            )

        if local in _JUNK_LOCAL:
            return EmailValidationResult(
                email=email, status=EmailStatus.INVALID,
                confidence=confidence, error="junk_local_part",
            )

        priority = "low" if local in _LOW_PRIORITY_LOCAL else "normal"

        # MX lookup
        mx_hosts, error = self._mx_lookup(domain)
        if error == "timeout":
            status = EmailStatus.UNVERIFIABLE
        elif mx_hosts:
            status = EmailStatus.VALID
        else:
            status = EmailStatus.INVALID

        return EmailValidationResult(
            email=email,
            status=status,
            confidence=confidence,
            priority=priority,
            mx_hosts=mx_hosts,
            error=error,
        )

    @staticmethod
    def _mx_lookup(domain: str) -> tuple[list[str], Optional[str]]:
        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, "MX", lifetime=5.0)
            hosts = sorted(
                str(r.exchange).rstrip(".") for r in answers
            )
            return hosts, None
        except Exception as exc:
            name = type(exc).__name__
            if "NoAnswer" in name or "NXDOMAIN" in name:
                return [], "no_mx"
            if "Timeout" in name or "NoNameservers" in name:
                return [], "timeout"
            return [], str(exc)


# ─── Phone validation ─────────────────────────────────────────────────────────

class PhoneStatus(str, Enum):
    VALID        = "valid"
    INVALID      = "invalid"
    UNVERIFIABLE = "unverifiable"


@dataclass
class PhoneValidationResult:
    raw: str
    e164: Optional[str]           # E.164 formatted, e.g. "+923001234567"
    status: PhoneStatus
    number_type: str              # MOBILE / FIXED_LINE / FIXED_LINE_OR_MOBILE / UNKNOWN / etc.
    whatsapp_eligible: bool       # True = valid mobile (or ambiguous)
    confidence: Confidence = Confidence.MEDIUM
    country_code: Optional[str] = None
    error: Optional[str] = None


class PhoneValidator:
    """
    Validates phone numbers using the `phonenumbers` library.

    whatsapp_eligible rules:
      MOBILE                → True
      FIXED_LINE_OR_MOBILE  → True  (ambiguous — must not be wrongly rejected)
      FIXED_LINE            → False
      everything else       → False
    """

    def __init__(self, default_region: str = "PK") -> None:
        self._default_region = default_region

    @staticmethod
    def infer_region(country: Optional[str] = None, city: Optional[str] = None) -> Optional[str]:
        target = f"{country or ''} {city or ''}".lower().strip()
        if not target:
            return None
        if any(w in target for w in ("pakistan", "karachi", "lahore", "islamabad", "rawalpindi", "faisalabad", "multan", "peshawar", "sialkot", "gujranwala", "quetta")):
            return "PK"
        if any(w in target for w in ("uae", "emirates", "dubai", "abu dhabi", "sharjah", "ajman", "ras al khaimah", "fujairah", "al ain")):
            return "AE"
        if any(w in target for w in ("saudi", "ksa", "riyadh", "jeddah", "mecca", "medina", "dammam", "khobar", "tabuk")):
            return "SA"
        if any(w in target for w in ("qatar", "doha", "al rayyan")):
            return "QA"
        if any(w in target for w in ("kuwait", "salmiya", "hawally")):
            return "KW"
        if any(w in target for w in ("bahrain", "manama")):
            return "BH"
        if any(w in target for w in ("oman", "muscat")):
            return "OM"
        if any(w in target for w in ("kingdom", "uk", "london", "manchester", "birmingham", "leeds", "glasgow", "liverpool", "edinburgh")):
            return "GB"
        if any(w in target for w in ("united states", "usa", "us", "york", "angeles", "chicago", "houston", "miami", "dallas", "seattle", "austin")):
            return "US"
        if any(w in target for w in ("canada", "toronto", "vancouver", "montreal", "calgary", "ottawa")):
            return "CA"
        if any(w in target for w in ("australia", "sydney", "melbourne", "brisbane", "perth")):
            return "AU"
        if any(w in target for w in ("germany", "berlin", "munich", "hamburg", "frankfurt")):
            return "DE"
        return None

    def validate(
        self,
        phone: str,
        confidence: Confidence = Confidence.MEDIUM,
        country: Optional[str] = None,
        city: Optional[str] = None,
    ) -> PhoneValidationResult:
        import phonenumbers
        from phonenumbers import PhoneNumberType, NumberParseException

        raw = phone.strip()
        inferred = self.infer_region(country, city)
        primary_region = inferred or self._default_region

        candidate_regions = [primary_region]
        for reg in ("AE", "SA", "QA", "KW", "PK", "GB", "US", "BH", "OM", "CA", "AU", "DE"):
            if reg not in candidate_regions:
                candidate_regions.append(reg)

        parsed = None
        last_exc = None

        # Clean digits for leading prefix checks
        digits = re.sub(r"\D", "", raw)
        phone_to_parse = raw
        if not phone_to_parse.startswith("+") and digits.startswith(("971", "966", "974", "965", "923", "447", "1")):
            phone_to_parse = "+" + digits

        for reg in candidate_regions:
            try:
                p = phonenumbers.parse(phone_to_parse, reg)
                if phonenumbers.is_valid_number(p):
                    parsed = p
                    break
            except NumberParseException as exc:
                last_exc = exc
                continue

        if not parsed:
            return PhoneValidationResult(
                raw=raw, e164=None, status=PhoneStatus.INVALID,
                number_type="UNKNOWN", whatsapp_eligible=False,
                confidence=confidence, error=str(last_exc) if last_exc else "invalid_number",
            )

        e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        ntype = phonenumbers.number_type(parsed)
        type_name = PhoneNumberType.to_string(ntype)

        whatsapp_eligible = ntype in (
            PhoneNumberType.MOBILE,
            PhoneNumberType.FIXED_LINE_OR_MOBILE,
        )

        country_code = phonenumbers.region_code_for_number(parsed)

        return PhoneValidationResult(
            raw=raw,
            e164=e164,
            status=PhoneStatus.VALID,
            number_type=type_name,
            whatsapp_eligible=whatsapp_eligible,
            confidence=confidence,
            country_code=country_code,
        )


# ─── Module-level singletons ──────────────────────────────────────────────────

_email_validator = EmailValidator(smtp_rcpt=False)
_phone_validator = PhoneValidator(default_region="PK")


def validate_email(
    email: str,
    confidence: Confidence = Confidence.MEDIUM,
) -> EmailValidationResult:
    return _email_validator.validate(email, confidence)


def validate_phone(
    phone: str,
    confidence: Confidence = Confidence.MEDIUM,
    default_region: str = "PK",
    country: Optional[str] = None,
    city: Optional[str] = None,
) -> PhoneValidationResult:
    v = PhoneValidator(default_region=default_region)
    return v.validate(phone, confidence, country=country, city=city)
