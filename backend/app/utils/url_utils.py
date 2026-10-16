"""
URL utility functions.

Functions
---------
normalize_url(url)        -> str | None
    Ensure a URL has a scheme; strip trailing slashes.
extract_domain(url)       -> str | None
    Return the bare registered domain (e.g. ``"example.com"``).
is_valid_url(url)         -> bool
    Quick syntactic check using urllib.parse.
is_parked_domain(url)     -> bool
    Heuristic detection of domain-parking / placeholder pages.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse, urlunparse

# ---------------------------------------------------------------------------
# Known parked / placeholder patterns
# ---------------------------------------------------------------------------

_PARKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "godaddy.com",
        "parkingcrew.net",
        "sedo.com",
        "bodis.com",
        "dan.com",
        "undeveloped.com",
        "hugedomains.com",
        "afternic.com",
        "domainmarket.com",
        "domcollect.com",
        "parked.com",
        "above.com",
        "domainnamessales.com",
        "domainnamesales.com",
    }
)

_PARKED_TITLE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"domain\s*(for\s*sale|is\s*for\s*sale|parked)", re.I),
    re.compile(r"buy\s*(this\s*)?domain", re.I),
    re.compile(r"this\s*domain\s*(is\s*)?(available|expired|registered)", re.I),
    re.compile(r"coming\s*soon", re.I),
    re.compile(r"under\s*construction", re.I),
    re.compile(r"website\s*coming\s*soon", re.I),
    re.compile(r"placeholder", re.I),
    re.compile(r"default\s*web\s*site\s*page", re.I),
    re.compile(r"apache\s*http\s*server", re.I),
    re.compile(r"nginx\s*default", re.I),
    re.compile(r"welcome\s*to\s*(nginx|apache|iis)", re.I),
)

# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------


def normalize_url(url: Optional[str]) -> Optional[str]:
    """
    Return a normalised version of *url* or ``None`` if it cannot be fixed.

    Normalisation steps
    -------------------
    1. Strip leading/trailing whitespace.
    2. Add ``https://`` scheme if none is present.
    3. Lower-case the scheme and host.
    4. Remove default ports (80 for http, 443 for https).
    5. Strip trailing slashes from the path.
    6. Remove fragment identifiers.
    """
    if not url:
        return None

    url = url.strip()

    # Drop bare fragments or javascript: links
    if url.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None

    # Add scheme if missing
    if "://" not in url:
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except Exception:
        return None

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return None

    netloc = parsed.netloc.lower()
    if not netloc:
        return None

    # Strip default ports
    if ":" in netloc:
        host, _, port = netloc.rpartition(":")
        if (scheme == "http" and port == "80") or (scheme == "https" and port == "443"):
            netloc = host

    path = parsed.path.rstrip("/") or ""

    normalised = urlunparse((scheme, netloc, path, "", parsed.query, ""))
    return normalised


# ---------------------------------------------------------------------------
# extract_domain
# ---------------------------------------------------------------------------


def extract_domain(url: Optional[str]) -> Optional[str]:
    """
    Extract the bare domain (host without ``www.`` prefix) from *url*.

    Returns ``None`` if *url* is invalid or has no host component.

    Examples
    --------
    >>> extract_domain("https://www.example.com/path?q=1")
    'example.com'
    >>> extract_domain("http://sub.example.co.uk/")
    'sub.example.co.uk'
    """
    if not url:
        return None

    norm = normalize_url(url)
    if not norm:
        return None

    try:
        host = urlparse(norm).netloc
    except Exception:
        return None

    # Strip port if present
    if ":" in host:
        host = host.rsplit(":", 1)[0]

    # Strip leading www.
    if host.startswith("www."):
        host = host[4:]

    return host.lower() if host else None


# ---------------------------------------------------------------------------
# is_valid_url
# ---------------------------------------------------------------------------


def is_valid_url(url: Optional[str]) -> bool:
    """
    Return ``True`` if *url* is syntactically valid and has a reachable scheme.

    This is a fast, purely syntactic check — it does not perform network I/O.
    """
    if not url:
        return False

    norm = normalize_url(url)
    if not norm:
        return False

    try:
        parsed = urlparse(norm)
        return bool(parsed.scheme in ("http", "https") and parsed.netloc)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# is_parked_domain
# ---------------------------------------------------------------------------

# Common placeholder / parked page path patterns
_PARKED_PATH_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"^/cgi-bin/", re.I),
)


def is_parked_domain(
    url: Optional[str],
    page_title: Optional[str] = None,
    page_content: Optional[str] = None,
) -> bool:
    """
    Heuristically determine whether *url* points to a parked or placeholder site.

    Parameters
    ----------
    url:
        The website URL to check.
    page_title:
        Optional ``<title>`` text fetched from the page for deeper inspection.
    page_content:
        Optional raw page body text for keyword matching.

    Returns
    -------
    bool
        ``True`` if the domain appears to be parked or otherwise not a real
        business website.
    """
    if not url:
        return False

    # Check if the host itself is a known parking registrar
    domain = extract_domain(url)
    if domain:
        for parked in _PARKED_HOSTNAMES:
            if domain == parked or domain.endswith("." + parked):
                return True

    # Title-based check
    if page_title:
        for pattern in _PARKED_TITLE_PATTERNS:
            if pattern.search(page_title):
                return True

    # Content keyword check (lightweight)
    if page_content:
        content_lower = page_content.lower()
        parked_phrases = (
            "this domain is for sale",
            "buy this domain",
            "domain parking",
            "this domain has expired",
            "domain is available",
        )
        for phrase in parked_phrases:
            if phrase in content_lower:
                return True

    return False
