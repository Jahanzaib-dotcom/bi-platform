"""
Revenue Estimator — industry/project/geo-aware project value estimation.

All dollar values are in USD.  Geographic multipliers adjust for purchasing-
power differences across markets.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Pricing tables
# ---------------------------------------------------------------------------

# Base price ranges (min, max) in USD for each project type.
_BASE_PRICES: Dict[str, tuple[float, float]] = {
    "new_website":          (2_500,   15_000),
    "redesign":             (3_000,   20_000),
    "seo":                  (800,      5_000),
    "seo_monthly":          (500,      3_000),  # per month retainer
    "mobile_optimization":  (1_500,    8_000),
    "accessibility":        (1_000,    6_000),
    "performance":          (1_200,    7_500),
    "ecommerce":            (5_000,   40_000),
    "landing_page":         (1_000,    5_000),
    "content_rewrite":      (500,      3_000),
    "branding":             (1_500,    8_000),
    "security_hardening":   (800,      4_000),
    "full_digital":         (8_000,   60_000),  # comprehensive engagement
    "maintenance_monthly":  (200,      1_500),   # per month
}

# Industry multipliers: factor applied on top of base price.
_INDUSTRY_MULTIPLIERS: Dict[str, float] = {
    # High-value / professional services
    "legal":            2.2,
    "finance":          2.0,
    "healthcare":       1.9,
    "real_estate":      1.8,
    "insurance":        1.7,
    "accounting":       1.6,
    "consulting":       1.5,
    # Technology / SaaS
    "technology":       1.8,
    "software":         1.7,
    "saas":             1.7,
    # E-commerce / retail
    "ecommerce":        1.6,
    "retail":           1.4,
    "fashion":          1.3,
    # Hospitality / travel
    "hospitality":      1.4,
    "travel":           1.3,
    "restaurant":       1.2,
    # Education
    "education":        1.3,
    "training":         1.2,
    # Construction / trades
    "construction":     1.3,
    "contractor":       1.2,
    "plumbing":         1.1,
    "electrician":      1.1,
    "hvac":             1.1,
    "roofing":          1.1,
    # Automotive
    "automotive":       1.4,
    "car_dealer":       1.5,
    # Health / wellness / beauty
    "wellness":         1.2,
    "beauty":           1.1,
    "salon":            1.0,
    "fitness":          1.1,
    # Food & beverage
    "food":             1.0,
    "bakery":           0.9,
    # Non-profit
    "nonprofit":        0.7,
    # Default fallback
    "default":          1.0,
}

# Country-level geo multipliers (base = US = 1.0).
_COUNTRY_MULTIPLIERS: Dict[str, float] = {
    "us":  1.00,
    "usa": 1.00,
    "united states": 1.00,
    "ca":  0.85,
    "canada": 0.85,
    "gb":  0.90,
    "uk":  0.90,
    "united kingdom": 0.90,
    "au":  0.80,
    "australia": 0.80,
    "nz":  0.75,
    "new zealand": 0.75,
    "ie":  0.80,
    "ireland": 0.80,
    "de":  0.85,
    "germany": 0.85,
    "fr":  0.80,
    "france": 0.80,
    "nl":  0.82,
    "netherlands": 0.82,
    "sg":  0.85,
    "singapore": 0.85,
    "ae":  0.90,
    "uae": 0.90,
    "ch":  0.95,
    "switzerland": 0.95,
    "jp":  0.78,
    "japan": 0.78,
    "in":  0.35,
    "india": 0.35,
    "pk":  0.30,
    "pakistan": 0.30,
    "bd":  0.28,
    "bangladesh": 0.28,
    "ng":  0.32,
    "nigeria": 0.32,
    "za":  0.40,
    "south africa": 0.40,
    "br":  0.45,
    "brazil": 0.45,
    "mx":  0.50,
    "mexico": 0.50,
    "ar":  0.40,
    "argentina": 0.40,
    "ph":  0.38,
    "philippines": 0.38,
    "my":  0.55,
    "malaysia": 0.55,
    "id":  0.35,
    "indonesia": 0.35,
    "eg":  0.32,
    "egypt": 0.32,
    "ke":  0.33,
    "kenya": 0.33,
}

# Additional city-tier adjustments applied ON TOP of country multiplier.
# These are additive deltas (e.g. +0.10 for NYC vs the US baseline).
_CITY_ADJUSTMENTS: Dict[str, float] = {
    # US major metros — premium
    "new york":          0.20,
    "new york city":     0.20,
    "nyc":               0.20,
    "san francisco":     0.20,
    "san jose":          0.15,
    "los angeles":       0.15,
    "la":                0.15,
    "seattle":           0.12,
    "boston":            0.12,
    "washington":        0.12,
    "dc":                0.12,
    "chicago":           0.10,
    "miami":             0.08,
    "austin":            0.08,
    "denver":            0.06,
    "atlanta":           0.05,
    "dallas":            0.05,
    "houston":           0.05,
    "phoenix":           0.02,
    # UK / Europe
    "london":            0.15,
    "zurich":            0.10,
    "amsterdam":         0.05,
    "paris":             0.05,
    "berlin":            0.03,
    # APAC
    "sydney":            0.10,
    "melbourne":         0.07,
    "singapore":         0.05,
    "hong kong":         0.08,
    "tokyo":             0.05,
    # Middle East
    "dubai":             0.10,
    "abu dhabi":         0.08,
}


class RevenueEstimator:
    """
    Estimates project revenue potential based on project type, industry, and
    geographic location.

    All returned monetary values are in USD.
    """

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def estimate_project_value(
        self,
        project_type: str,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return a value-range estimate for a project.

        Returns:
            {
                "project_type": str,
                "min": float,
                "max": float,
                "midpoint": float,
                "currency": "USD",
                "industry_multiplier": float,
                "geo_multiplier": float,
                "effective_multiplier": float,
            }
        """
        base_min, base_max = _BASE_PRICES.get(
            project_type.lower().replace(" ", "_"),
            _BASE_PRICES["redesign"],  # sensible fallback
        )

        industry_mult = self.get_industry_multiplier(industry)
        geo_mult = self.get_geo_multiplier(country, city)
        effective_mult = industry_mult * geo_mult

        adjusted_min = round(base_min * effective_mult, 2)
        adjusted_max = round(base_max * effective_mult, 2)
        midpoint = round((adjusted_min + adjusted_max) / 2, 2)

        return {
            "project_type": project_type,
            "min": adjusted_min,
            "max": adjusted_max,
            "midpoint": midpoint,
            "currency": "USD",
            "industry_multiplier": round(industry_mult, 4),
            "geo_multiplier": round(geo_mult, 4),
            "effective_multiplier": round(effective_mult, 4),
        }

    def get_industry_multiplier(self, industry: Optional[str]) -> float:
        """
        Return the pricing multiplier for the given industry string.

        Performs case-insensitive substring matching so that "Healthcare IT"
        matches the "healthcare" key.
        """
        if not industry:
            return _INDUSTRY_MULTIPLIERS["default"]

        normalized = industry.lower().strip()

        # Exact match first.
        if normalized in _INDUSTRY_MULTIPLIERS:
            return _INDUSTRY_MULTIPLIERS[normalized]

        # Substring match — pick the highest multiplier found.
        best: Optional[float] = None
        for key, mult in _INDUSTRY_MULTIPLIERS.items():
            if key == "default":
                continue
            if key in normalized or normalized in key:
                if best is None or mult > best:
                    best = mult

        return best if best is not None else _INDUSTRY_MULTIPLIERS["default"]

    def get_geo_multiplier(
        self,
        country: Optional[str],
        city: Optional[str] = None,
    ) -> float:
        """
        Return a combined country + city multiplier.

        Country is the dominant factor; the city adjustment is additive on top.
        """
        country_mult = 1.0
        if country:
            normalized = country.lower().strip()
            country_mult = _COUNTRY_MULTIPLIERS.get(normalized, 1.0)

            # Try 2-letter ISO code as fallback.
            if country_mult == 1.0 and len(normalized) > 2:
                iso2 = normalized[:2]
                country_mult = _COUNTRY_MULTIPLIERS.get(iso2, 1.0)

        city_adj = 0.0
        if city:
            normalized_city = city.lower().strip()
            city_adj = _CITY_ADJUSTMENTS.get(normalized_city, 0.0)

            if city_adj == 0.0:
                # Partial match.
                for key, adj in _CITY_ADJUSTMENTS.items():
                    if key in normalized_city or normalized_city in key:
                        city_adj = adj
                        break

        return max(0.1, country_mult + city_adj)

    def estimate_full_engagement(
        self,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        country: Optional[str] = None,
        project_types: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """
        Estimate total value of multiple project types bundled together.

        If project_types is None, uses a standard engagement bundle
        (redesign + SEO + maintenance).
        """
        if project_types is None:
            project_types = ["redesign", "seo", "maintenance_monthly"]

        breakdown: Dict[str, Any] = {}
        total_min = 0.0
        total_max = 0.0

        for pt in project_types:
            estimate = self.estimate_project_value(pt, industry, city, country)
            breakdown[pt] = estimate
            total_min += estimate["min"]
            total_max += estimate["max"]

        return {
            "total_min": round(total_min, 2),
            "total_max": round(total_max, 2),
            "total_midpoint": round((total_min + total_max) / 2, 2),
            "currency": "USD",
            "breakdown": breakdown,
            "industry_multiplier": self.get_industry_multiplier(industry),
            "geo_multiplier": self.get_geo_multiplier(country, city),
        }

    @staticmethod
    def list_project_types() -> list[str]:
        """Return all known project type keys."""
        return sorted(_BASE_PRICES.keys())

    @staticmethod
    def list_industries() -> list[str]:
        """Return all known industry keys (excluding 'default')."""
        return [k for k in sorted(_INDUSTRY_MULTIPLIERS.keys()) if k != "default"]
