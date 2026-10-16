"""
Business-domain utility functions.

Functions
---------
generate_slug(name, suffix_length)   -> str
    Generate a URL-safe slug from a business name, appending a short hex suffix
    to guarantee uniqueness.
fingerprint_business(name, city, phone, website_url) -> str
    Return a stable SHA-256 fingerprint of a business's key identity fields,
    used for fast duplicate detection without a DB lookup.
clean_phone(raw_phone)               -> str | None
    Normalise a raw phone string to E.164 format (``+15551234567``) or return
    ``None`` if it cannot be parsed.
clean_address(raw_address)           -> str | None
    Strip excess whitespace, normalise separators, and title-case components.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from typing import Optional

# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------

_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")
_LEADING_TRAILING_DASH = re.compile(r"^-+|-+$")
_MULTIPLE_DASHES = re.compile(r"-{2,}")


def generate_slug(name: str, suffix_length: int = 8) -> str:
    """
    Create a URL-safe, lowercase, hyphen-separated slug from *name*.

    A short random hex suffix (default 8 characters) is appended to reduce
    collision probability when inserting into the database without a prior
    uniqueness check.

    Parameters
    ----------
    name:
        Human-readable business name, e.g. ``"O'Brien's Café & Grill"``.
    suffix_length:
        Length of the hex suffix appended after a hyphen (default 8).

    Returns
    -------
    str
        e.g. ``"obriens-cafe-grill-a3f9b2c1"``
    """
    if not name:
        return uuid.uuid4().hex[:suffix_length]

    # Normalise unicode to ASCII equivalents (e.g. é -> e)
    normalised = unicodedata.normalize("NFKD", name)
    ascii_str = normalised.encode("ascii", errors="ignore").decode("ascii")

    slug = ascii_str.lower()
    slug = _NON_SLUG_RE.sub("-", slug)
    slug = _LEADING_TRAILING_DASH.sub("", slug)
    slug = _MULTIPLE_DASHES.sub("-", slug)
    slug = slug[:200]  # guard against absurdly long names

    if not slug:
        slug = "business"

    suffix = uuid.uuid4().hex[:suffix_length]
    return f"{slug}-{suffix}"


# ---------------------------------------------------------------------------
# Business fingerprinting
# ---------------------------------------------------------------------------

_WS_RE = re.compile(r"\s+")


def fingerprint_business(
    name: Optional[str],
    city: Optional[str] = None,
    phone: Optional[str] = None,
    website_url: Optional[str] = None,
) -> str:
    """
    Return a stable 64-character hex SHA-256 fingerprint for a business record.

    The fingerprint is computed over the normalised, concatenated key identity
    fields so that two records describing the same real-world entity will
    produce the same fingerprint regardless of how they were entered.

    Normalisation applied per field
    --------------------------------
    * Whitespace collapsed to single spaces, stripped.
    * Lower-cased.
    * For ``website_url``: scheme, ``www.`` prefix, and trailing slash stripped.
    * For ``phone``: non-digit characters stripped.

    Parameters
    ----------
    name:
        Business trading name (required; empty string treated as ``"unknown"``).
    city:
        City of operation (optional).
    phone:
        Phone number in any format (optional).
    website_url:
        Business website URL (optional).

    Returns
    -------
    str
        64-character lowercase hexadecimal SHA-256 digest.
    """

    def _norm(value: Optional[str]) -> str:
        if not value:
            return ""
        return _WS_RE.sub(" ", value.strip().lower())

    def _norm_phone(value: Optional[str]) -> str:
        if not value:
            return ""
        return re.sub(r"\D", "", value)

    def _norm_url(value: Optional[str]) -> str:
        if not value:
            return ""
        url = value.strip().lower()
        url = re.sub(r"^https?://", "", url)
        url = re.sub(r"^www\.", "", url)
        url = url.rstrip("/")
        return url

    parts = [
        _norm(name) or "unknown",
        _norm(city),
        _norm_phone(phone),
        _norm_url(website_url),
    ]
    combined = "|".join(parts)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Phone cleaning
# ---------------------------------------------------------------------------

_DIGITS_RE = re.compile(r"\D")
_EXTENSION_RE = re.compile(r"(?:ext|x|#)[\s.:]?\d+$", re.I)

# Country dial-code prefix mapping (ISO-2 -> dial code prefix, length hint)
_COUNTRY_CODES: dict[str, str] = {
    "US": "1",
    "CA": "1",
    "GB": "44",
    "AU": "61",
    "DE": "49",
    "FR": "33",
    "IN": "91",
    "PK": "92",
    "AE": "971",
    "SA": "966",
}


def clean_phone(
    raw_phone: Optional[str],
    default_country: str = "US",
) -> Optional[str]:
    """
    Normalise a raw phone number string to E.164 format.

    Parameters
    ----------
    raw_phone:
        Phone number in any common format, e.g.
        ``"(555) 123-4567"``, ``"+1-800-555-0199"``, ``"0044 20 7946 0958"``.
    default_country:
        ISO-3166-1 alpha-2 country code used when no international prefix is
        detected (default ``"US"``).

    Returns
    -------
    str | None
        E.164 string such as ``"+15551234567"`` or ``None`` if the input
        cannot be parsed into a plausible phone number.
    """
    if not raw_phone:
        return None

    # Strip extensions
    cleaned = _EXTENSION_RE.sub("", raw_phone.strip())

    # Try to use phonenumbers library for accurate parsing if available
    try:
        import phonenumbers  # type: ignore

        try:
            parsed = phonenumbers.parse(cleaned, default_country)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.NumberParseException:
            pass
    except ImportError:
        pass

    # Fallback: manual digit extraction
    digits = _DIGITS_RE.sub("", cleaned)
    if not digits:
        return None

    # Handle international prefix
    if raw_phone.strip().startswith("+"):
        if 7 <= len(digits) <= 15:
            return f"+{digits}"
        return None

    # Strip leading trunk 0 for UK / European numbers
    if digits.startswith("00"):
        digits = digits[2:]
        if 7 <= len(digits) <= 15:
            return f"+{digits}"
        return None

    # Apply default country code
    dial_code = _COUNTRY_CODES.get(default_country.upper(), "1")

    # Remove leading country code if already present
    if digits.startswith(dial_code) and len(digits) > len(dial_code) + 6:
        digits = digits[len(dial_code):]

    full = dial_code + digits
    if 8 <= len(full) <= 15:
        return f"+{full}"

    return None


# ---------------------------------------------------------------------------
# Address cleaning
# ---------------------------------------------------------------------------

_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_COMMA_RE = re.compile(r",\s*,+")
_TRAILING_COMMA_RE = re.compile(r",\s*$")
_SEPARATORS_RE = re.compile(r"\s*[,|;]\s*")

# Common address abbreviation expansions
_ABBREVIATIONS: dict[str, str] = {
    r"\bSt\b": "Street",
    r"\bAve\b": "Avenue",
    r"\bBlvd\b": "Boulevard",
    r"\bDr\b": "Drive",
    r"\bRd\b": "Road",
    r"\bCt\b": "Court",
    r"\bLn\b": "Lane",
    r"\bPl\b": "Place",
    r"\bSq\b": "Square",
    r"\bFwy\b": "Freeway",
    r"\bHwy\b": "Highway",
    r"\bPkwy\b": "Parkway",
    r"\bApt\b": "Apt",
    r"\bSte\b": "Suite",
    r"\bFl\b": "Floor",
}


def clean_address(raw_address: Optional[str]) -> Optional[str]:
    """
    Normalise an address string for consistent storage.

    Operations applied
    ------------------
    1. Strip leading/trailing whitespace.
    2. Collapse internal multi-spaces to a single space.
    3. Normalise separator punctuation (commas, pipes, semicolons).
    4. Remove redundant commas.
    5. Title-case each component (word boundary capitalisation).
    6. Return ``None`` if the result is empty or suspiciously short (< 5 chars).

    Parameters
    ----------
    raw_address:
        Freeform address string from an external source.

    Returns
    -------
    str | None
        Cleaned address or ``None`` if the input is blank / unusable.
    """
    if not raw_address:
        return None

    addr = raw_address.strip()
    if not addr:
        return None

    # Normalise whitespace
    addr = _MULTI_SPACE_RE.sub(" ", addr)

    # Replace separators with ", "
    addr = _SEPARATORS_RE.sub(", ", addr)

    # Remove duplicate/trailing commas
    addr = _MULTI_COMMA_RE.sub(",", addr)
    addr = _TRAILING_COMMA_RE.sub("", addr).strip()

    # Title-case (preserves all-caps abbreviations like USA, UK)
    parts = [p.strip() for p in addr.split(",")]
    title_parts: list[str] = []
    for part in parts:
        # Only title-case parts that aren't already mixed-case abbreviations
        words = part.split()
        titled_words: list[str] = []
        for word in words:
            # Keep words that are fully uppercase and short (e.g. NY, TX, USA)
            if word.isupper() and len(word) <= 4:
                titled_words.append(word)
            else:
                titled_words.append(word.capitalize())
        title_parts.append(" ".join(titled_words))
    addr = ", ".join(p for p in title_parts if p)

    if len(addr) < 5:
        return None

    return addr
