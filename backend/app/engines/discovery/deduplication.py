"""Business deduplication utilities for the discovery engine."""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from typing import List, Optional, Set, Tuple
from urllib.parse import urlparse

from app.engines.discovery.base import BusinessResult


def _extract_domain(url: Optional[str]) -> Optional[str]:
    """Return the bare hostname from a URL, or None."""
    if not url:
        return None
    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = parsed.hostname or ""
        # Strip www. prefix
        return re.sub(r"^www\.", "", host.lower()) or None
    except Exception:
        return None


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two lat/lng points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _levenshtein(s1: str, s2: str) -> int:
    """Return the Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    len1, len2 = len(s1), len(s2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1

    # Use a rolling two-row DP table to keep memory O(min(len1, len2))
    if len1 < len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    prev = list(range(len2 + 1))
    for i, ch1 in enumerate(s1, 1):
        curr = [i] + [0] * len2
        for j, ch2 in enumerate(s2, 1):
            cost = 0 if ch1 == ch2 else 1
            curr[j] = min(
                curr[j - 1] + 1,       # insertion
                prev[j] + 1,           # deletion
                prev[j - 1] + cost,    # substitution
            )
        prev = curr

    return prev[len2]


def _similarity(s1: str, s2: str) -> float:
    """Return a 0–1 similarity score (1 = identical) based on Levenshtein."""
    if not s1 and not s2:
        return 1.0
    max_len = max(len(s1), len(s2))
    if max_len == 0:
        return 1.0
    return 1.0 - _levenshtein(s1, s2) / max_len


def _normalise_string(value: Optional[str]) -> str:
    """
    Lower-case, strip accents, collapse whitespace, and remove common
    legal suffixes (LLC, Ltd, Inc …) for comparison purposes.
    """
    if not value:
        return ""
    # Unicode normalisation – decompose accented characters
    nfkd = unicodedata.normalize("NFKD", value)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    lower = ascii_only.lower()
    # Remove punctuation except spaces
    cleaned = re.sub(r"[^\w\s]", " ", lower)
    # Strip legal suffixes
    cleaned = re.sub(
        r"\b(llc|ltd|limited|inc|incorporated|corp|corporation|co|company|group|holdings?)\b",
        "",
        cleaned,
    )
    return re.sub(r"\s+", " ", cleaned).strip()


class BusinessDeduplicator:
    """
    Tracks seen businesses and detects duplicates using:
    1. Exact SHA-256 fingerprint (name + city + country)
    2. Fuzzy name similarity within the same city
    3. Same domain (website) → always a duplicate
    4. Coordinate proximity < 50 m + similar name → duplicate

    Usage::

        dedup = BusinessDeduplicator(fuzzy_threshold=0.85)
        for result in results:
            if not dedup.is_duplicate(result):
                process(result)
    """

    # Two points within this distance (metres) with similar names = same business
    _COORD_PROXIMITY_M = 50.0

    def __init__(self, fuzzy_threshold: float = 0.85) -> None:
        if not 0.0 <= fuzzy_threshold <= 1.0:
            raise ValueError("fuzzy_threshold must be between 0 and 1")
        self._threshold = fuzzy_threshold
        self._seen_fingerprints: Set[str] = set()
        self._seen_domains: Set[str] = set()
        # (normalised_name, normalised_city, lat, lon)
        self._seen_names: List[Tuple[str, str, Optional[float], Optional[float]]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fingerprint(self, business: BusinessResult) -> str:
        """
        Compute a deterministic fingerprint for *business*.

        The fingerprint is the hex-encoded SHA-256 hash of the
        normalised ``name + "|" + city + "|" + country`` string so that
        minor formatting differences (e.g. trailing spaces, case) do not
        produce distinct fingerprints for the same entity.
        """
        norm_name = _normalise_string(business.name)
        norm_city = _normalise_string(business.city)
        norm_country = _normalise_string(business.country)
        raw = f"{norm_name}|{norm_city}|{norm_country}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def is_duplicate(self, business: BusinessResult) -> bool:
        """
        Return ``True`` if *business* has been seen before.
        Registers the business as seen on first encounter.

        Checks (in order):
        1. Exact fingerprint (name+city+country)
        2. Same domain
        3. Coordinate proximity < 50 m + fuzzy name match
        4. Fuzzy name match within same city
        """
        fp = self.fingerprint(business)
        if fp in self._seen_fingerprints:
            return True

        # Domain dedup — same website = same business regardless of name
        domain = _extract_domain(business.website_url)
        if domain and domain in self._seen_domains:
            return True

        norm_name = _normalise_string(business.name)
        norm_city = _normalise_string(business.city)
        lat = business.latitude
        lon = business.longitude

        for seen_name, seen_city, seen_lat, seen_lon in self._seen_names:
            # Coordinate proximity check
            if (lat is not None and lon is not None
                    and seen_lat is not None and seen_lon is not None):
                dist = _haversine_m(lat, lon, seen_lat, seen_lon)
                if dist < self._COORD_PROXIMITY_M and _similarity(norm_name, seen_name) >= 0.70:
                    return True

            # Fuzzy name check within same city
            city_match = (seen_city == norm_city or not seen_city or not norm_city)
            if city_match and _similarity(norm_name, seen_name) >= self._threshold:
                return True

        # Register as seen
        self._seen_fingerprints.add(fp)
        if domain:
            self._seen_domains.add(domain)
        self._seen_names.append((norm_name, norm_city, lat, lon))
        return False

    def merge_duplicates(self, businesses: List[BusinessResult]) -> List[BusinessResult]:
        """
        Given an unsorted list of :class:`BusinessResult` objects, return
        a deduplicated list.

        When two records are considered duplicates the one with **more
        filled fields** is preferred (higher data density wins).
        """
        # Group by fingerprint first (exact), then apply fuzzy merging
        groups: dict[str, List[BusinessResult]] = {}
        for biz in businesses:
            fp = self.fingerprint(biz)
            groups.setdefault(fp, []).append(biz)

        # Merge exact duplicates
        merged: List[BusinessResult] = [
            self._best_of(group) for group in groups.values()
        ]

        # Fuzzy-merge the already-exact-deduped list
        result: List[BusinessResult] = []
        dedup = BusinessDeduplicator(self._threshold)
        for biz in merged:
            if not dedup.is_duplicate(biz):
                result.append(biz)

        return result

    def reset(self) -> None:
        """Clear the internal seen-set so the deduplicator can be reused."""
        self._seen_fingerprints.clear()
        self._seen_domains.clear()
        self._seen_names.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _field_count(biz: BusinessResult) -> int:
        """Count non-empty fields (higher = richer record)."""
        fields = [
            biz.name,
            biz.address,
            biz.city,
            biz.state,
            biz.country,
            biz.phone,
            biz.email,
            biz.website_url,
            biz.category,
            biz.source_id,
        ]
        return sum(1 for f in fields if f)

    @classmethod
    def _best_of(cls, group: List[BusinessResult]) -> BusinessResult:
        """Return the record with the most populated fields."""
        return max(group, key=cls._field_count)
