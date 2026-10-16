"""
Scoring Engine — converts raw audit data into actionable business intelligence.

Responsibilities:
- Compute overall website quality scores from sub-scores.
- Estimate opportunity and priority scores for outbound sales.
- Estimate revenue potential from project type + geo + industry.
- Rank a list of businesses by priority.
- Surface specific actionable opportunities.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.engines.scoring.revenue_estimator import RevenueEstimator

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REVENUE_ESTIMATOR = RevenueEstimator()

_MODERN_TECH_KEYWORDS = {
    "react", "next.js", "nextjs", "vue", "nuxt", "angular", "svelte",
    "gatsby", "astro", "tailwind", "bootstrap 5", "webflow", "framer",
}
_LEGACY_TECH_KEYWORDS = {
    "jquery", "flash", "silverlight", "table layout", "font element",
    "frames", "frameset", "ie6", "ie7", "ie8", "ie9",
}
_MODERN_CMS = {"wordpress 6", "shopify", "webflow", "squarespace", "wix"}
_LEGACY_CMS  = {"joomla", "drupal 7", "drupal 6", "mambo", "oscommerce"}

# Industry competition index — higher = more competitive = less relative
# opportunity from a weak website alone (strong players dominate anyway).
_INDUSTRY_COMPETITION: Dict[str, float] = {
    "legal":        0.85,
    "finance":      0.80,
    "healthcare":   0.75,
    "real_estate":  0.70,
    "ecommerce":    0.90,
    "technology":   0.90,
    "restaurant":   0.60,
    "construction": 0.55,
    "salon":        0.50,
    "plumbing":     0.55,
    "electrician":  0.55,
    "hvac":         0.55,
    "default":      0.65,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _safe_score(val: Optional[float], default: float = 50.0) -> float:
    """Return val if present and in [0, 100], else default."""
    if val is None:
        return default
    return _clamp(float(val))


def _get_industry_competition(industry: Optional[str]) -> float:
    if not industry:
        return _INDUSTRY_COMPETITION["default"]
    key = industry.lower().strip()
    if key in _INDUSTRY_COMPETITION:
        return _INDUSTRY_COMPETITION[key]
    for k, v in _INDUSTRY_COMPETITION.items():
        if k == "default":
            continue
        if k in key or key in k:
            return v
    return _INDUSTRY_COMPETITION["default"]


# ---------------------------------------------------------------------------
# Score weights
# ---------------------------------------------------------------------------

@dataclass
class ScoreWeights:
    """
    Weights used when computing the overall website quality score.
    Values must sum to 1.0.  The defaults encode our judgment of relative
    importance for a typical small-business website.
    """
    ui:            float = 0.15
    ux:            float = 0.15
    mobile:        float = 0.12
    seo:           float = 0.15
    accessibility: float = 0.08
    performance:   float = 0.10
    security:      float = 0.08
    branding:      float = 0.07
    content:       float = 0.05
    conversion:    float = 0.05

    def __post_init__(self) -> None:
        total = (
            self.ui + self.ux + self.mobile + self.seo +
            self.accessibility + self.performance + self.security +
            self.branding + self.content + self.conversion
        )
        if not math.isclose(total, 1.0, rel_tol=1e-4):
            raise ValueError(
                f"ScoreWeights must sum to 1.0, got {total:.4f}"
            )

    def as_dict(self) -> Dict[str, float]:
        return {
            "ui": self.ui,
            "ux": self.ux,
            "mobile": self.mobile,
            "seo": self.seo,
            "accessibility": self.accessibility,
            "performance": self.performance,
            "security": self.security,
            "branding": self.branding,
            "content": self.content,
            "conversion": self.conversion,
        }


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class ScoringEngine:
    """
    Central engine that turns AuditReport + Business ORM objects (or plain
    dicts/duck-typed objects) into scored, ranked, opportunity-surfaced output.
    """

    def __init__(self, weights: Optional[ScoreWeights] = None) -> None:
        self.weights = weights or ScoreWeights()
        self._revenue_estimator = _REVENUE_ESTIMATOR

    # ------------------------------------------------------------------ #
    # 1. Website quality score
    # ------------------------------------------------------------------ #

    def calculate_website_quality_score(self, audit_report: Any) -> float:
        """
        Weighted average of all audit sub-scores.

        Returns a float in [0, 100].  Missing scores default to 50 so that
        absent data does not artificially inflate or deflate the result.
        """
        w = self.weights

        ui    = _safe_score(getattr(audit_report, "ui_score", None))
        ux    = _safe_score(getattr(audit_report, "ux_score", None))
        mob   = _safe_score(getattr(audit_report, "mobile_score", None))
        seo   = _safe_score(getattr(audit_report, "seo_score", None))
        acc   = _safe_score(getattr(audit_report, "accessibility_score", None))
        perf  = _safe_score(getattr(audit_report, "speed_score", None))
        sec   = _safe_score(getattr(audit_report, "security_score", None))
        brand = _safe_score(getattr(audit_report, "branding_score", None))
        cont  = _safe_score(getattr(audit_report, "content_score", None))
        conv  = _safe_score(getattr(audit_report, "conversion_score", None))

        score = (
            ui    * w.ui +
            ux    * w.ux +
            mob   * w.mobile +
            seo   * w.seo +
            acc   * w.accessibility +
            perf  * w.performance +
            sec   * w.security +
            brand * w.branding +
            cont  * w.content +
            conv  * w.conversion
        )
        return round(_clamp(score), 2)

    # ------------------------------------------------------------------ #
    # 2. Opportunity score
    # ------------------------------------------------------------------ #

    def calculate_opportunity_score(
        self,
        business: Any,
        audit_report: Any,
    ) -> float:
        """
        Higher score = MORE opportunity.

        A weak website in a competitive, high-value industry with a young
        domain represents the best opportunity for a web agency.

        Components (all normalised to 0-100 before weighting):
        - website_quality_gap  (40%): how bad the site is
        - industry_value       (25%): revenue multiplier for the industry
        - competition_factor   (15%): how competitive the market is
        - recency_factor       (20%): how recently the site was last updated
        """
        quality = self.calculate_website_quality_score(audit_report)
        # Gap: a score of 0 = max gap, 100 = no gap
        quality_gap = _clamp(100.0 - quality)

        # Industry value — map the revenue estimator's multiplier to 0-100.
        industry = getattr(business, "industry", None) or getattr(business, "category", None)
        raw_mult = self._revenue_estimator.get_industry_multiplier(industry)
        # Typical range 0.7 – 2.2; we normalise to [0, 100] with 1.0 = 50.
        industry_value = _clamp((raw_mult - 0.7) / (2.2 - 0.7) * 100.0)

        # Competition factor — high competition raises opportunity slightly
        # (more businesses spending on SEO/web = validated market).
        comp = _get_industry_competition(industry)
        competition_factor = _clamp(comp * 100.0)

        # Recency factor — sites that haven't been touched in years
        # are riper for a redesign pitch.
        recency_factor = self._compute_recency_factor(audit_report)

        score = (
            quality_gap       * 0.40 +
            industry_value    * 0.25 +
            competition_factor * 0.15 +
            recency_factor    * 0.20
        )
        return round(_clamp(score), 2)

    def _compute_recency_factor(self, audit_report: Any) -> float:
        """
        Return 0-100 indicating how outdated the site is (higher = more stale).

        Uses tech_stack data and/or site audit timing as a heuristic.
        """
        tech_stack: Optional[List[Dict]] = getattr(audit_report, "tech_stack", None)
        if not tech_stack:
            return 50.0  # unknown — neutral

        # Look for year hints in tech names (e.g. "WordPress 4.9", "jQuery 1.x").
        current_year = datetime.now(tz=timezone.utc).year
        years_found: List[int] = []
        for tech in tech_stack:
            name = str(tech.get("name", "") or "").lower()
            version = str(tech.get("version", "") or "")
            # Extract leading integer from version string.
            parts = version.split(".")
            if parts and parts[0].isdigit():
                major = int(parts[0])
                # Very rough: if major version maps to a year (e.g. v1 in 2010)
                # we use a lookup; otherwise we note the major.
                years_found.append(major)

            # Count legacy tech as ageing signal.
            for legacy in _LEGACY_TECH_KEYWORDS:
                if legacy in name:
                    return 80.0  # clearly outdated

        modernity = self.calculate_modernization_score(audit_report)
        # Invert: a very modern site has low recency_factor.
        return _clamp(100.0 - modernity)

    # ------------------------------------------------------------------ #
    # 3. Priority score
    # ------------------------------------------------------------------ #

    def calculate_priority_score(
        self,
        business: Any,
        audit_report: Any,
    ) -> float:
        """
        Combines opportunity + revenue potential + ease of win.

        Returns 0-100 where 100 = top priority prospect.
        """
        opportunity = self.calculate_opportunity_score(business, audit_report)

        # Revenue potential: use midpoint estimate normalised to 0-100 where
        # $50 000 = 100.
        rev = self.estimate_revenue_potential(business, audit_report)
        midpoint = (rev["min"] + rev["max"]) / 2.0
        revenue_factor = _clamp(midpoint / 50_000.0 * 100.0)

        # Ease-of-win heuristic: small business with no social proof =
        # easier to win; large enterprise with strong web presence = harder.
        ease = self._compute_ease_of_win(business, audit_report)

        score = (
            opportunity    * 0.50 +
            revenue_factor * 0.30 +
            ease           * 0.20
        )
        return round(_clamp(score), 2)

    def _compute_ease_of_win(self, business: Any, audit_report: Any) -> float:
        """
        Heuristic 0-100 ease-of-win score.

        - Business has no social profiles → easier (less digital savvy)
        - Site has critical issues → easier (obvious pain)
        - Site was last audited a long time ago → they may be inactive
        """
        score = 50.0

        # Social presence: no social = less digitally mature = easier
        social = getattr(business, "social_profiles", None) or {}
        active_socials = sum(1 for v in social.values() if v)
        score -= active_socials * 3.0  # each active profile lowers ease slightly

        # Critical issues boost ease.
        seo_issues = getattr(audit_report, "seo_issues", None) or []
        acc_issues = getattr(audit_report, "accessibility_issues", None) or []
        critical = sum(
            1 for i in (seo_issues + acc_issues)
            if str(i.get("severity", "") or i.get("impact", "")).lower()
               in ("critical", "serious")
        )
        score += min(critical * 5.0, 30.0)

        # No website at all → maximum ease (blank slate pitch).
        if not getattr(audit_report, "website_url", None):
            score = 90.0

        return _clamp(score)

    # ------------------------------------------------------------------ #
    # 4. Revenue potential
    # ------------------------------------------------------------------ #

    def estimate_revenue_potential(
        self,
        business: Any,
        audit_report: Any,
    ) -> Dict[str, Any]:
        """
        Estimate realistic project value range for this business.

        Returns:
            {
                "min": float,
                "max": float,
                "currency": "USD",
                "breakdown": dict,
            }
        """
        industry = (
            getattr(business, "industry", None) or
            getattr(business, "category", None)
        )
        city    = getattr(business, "city", None)
        country = getattr(business, "country", None)

        # Decide which project types apply based on audit findings.
        project_types = self._infer_project_types(business, audit_report)

        result = self._revenue_estimator.estimate_full_engagement(
            industry=industry,
            city=city,
            country=country,
            project_types=project_types,
        )
        return {
            "min": result["total_min"],
            "max": result["total_max"],
            "currency": "USD",
            "breakdown": result["breakdown"],
        }

    def _infer_project_types(
        self,
        business: Any,
        audit_report: Any,
    ) -> List[str]:
        """
        Determine which project types are relevant given audit findings.
        """
        types: List[str] = []

        has_website = getattr(business, "has_website", True)
        if not has_website:
            return ["new_website"]

        quality = self.calculate_website_quality_score(audit_report)
        if quality < 40:
            types.append("redesign")
        elif quality < 60:
            types.append("redesign")

        seo = _safe_score(getattr(audit_report, "seo_score", None), default=50.0)
        if seo < 60:
            types.append("seo")

        mobile = _safe_score(getattr(audit_report, "mobile_score", None), default=50.0)
        if mobile < 60:
            types.append("mobile_optimization")

        acc = _safe_score(getattr(audit_report, "accessibility_score", None), default=50.0)
        if acc < 50:
            types.append("accessibility")

        perf = _safe_score(getattr(audit_report, "speed_score", None), default=50.0)
        if perf < 50:
            types.append("performance")

        # Always include maintenance.
        types.append("maintenance_monthly")

        # Deduplicate while preserving order.
        seen: set = set()
        deduped = []
        for t in types:
            if t not in seen:
                seen.add(t)
                deduped.append(t)

        return deduped if deduped else ["redesign", "seo", "maintenance_monthly"]

    # ------------------------------------------------------------------ #
    # 5. Modernization score
    # ------------------------------------------------------------------ #

    def calculate_modernization_score(self, audit_report: Any) -> float:
        """
        How modern/current the website appears.

        Returns 0-100 where 100 = cutting-edge modern stack.

        Uses:
        - tech_stack detections
        - Year-based heuristics from tech versions
        - Performance metrics (modern sites tend to be faster)
        """
        score = 50.0  # neutral default

        tech_stack: Optional[List[Dict]] = getattr(audit_report, "tech_stack", None)
        if tech_stack:
            modern_hits  = 0
            legacy_hits  = 0
            for tech in tech_stack:
                name = str(tech.get("name", "") or "").lower()
                for kw in _MODERN_TECH_KEYWORDS:
                    if kw in name:
                        modern_hits += 1
                        break
                for kw in _LEGACY_TECH_KEYWORDS:
                    if kw in name:
                        legacy_hits += 1
                        break

            # Each modern hit adds 8 points; each legacy hit subtracts 12.
            score += modern_hits * 8.0
            score -= legacy_hits * 12.0

        # Performance proxy: fast sites tend to use modern tooling.
        perf = getattr(audit_report, "speed_score", None)
        if perf is not None:
            perf_f = _safe_score(perf)
            # If very fast (>80) add a small bonus; if very slow (<30) subtract.
            if perf_f >= 80:
                score += 10.0
            elif perf_f < 30:
                score -= 10.0

        # Mobile responsiveness is a proxy for modern design.
        mob = getattr(audit_report, "mobile_score", None)
        if mob is not None:
            mob_f = _safe_score(mob)
            if mob_f >= 80:
                score += 8.0
            elif mob_f < 40:
                score -= 10.0

        return round(_clamp(score), 2)

    # ------------------------------------------------------------------ #
    # 6. Rank businesses
    # ------------------------------------------------------------------ #

    def rank_businesses(
        self,
        businesses_with_audits: List[Tuple[Any, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Sort a list of (Business, AuditReport) tuples by priority_score
        descending.

        Returns a list of dicts:
            [{
                "business": <Business>,
                "audit_report": <AuditReport>,
                "quality_score": float,
                "opportunity_score": float,
                "priority_score": float,
                "revenue_potential": dict,
                "modernization_score": float,
                "opportunities": list,
            }]
        """
        ranked: List[Dict[str, Any]] = []

        for business, audit_report in businesses_with_audits:
            try:
                quality      = self.calculate_website_quality_score(audit_report)
                opportunity  = self.calculate_opportunity_score(business, audit_report)
                priority     = self.calculate_priority_score(business, audit_report)
                revenue      = self.estimate_revenue_potential(business, audit_report)
                modernization = self.calculate_modernization_score(audit_report)
                opportunities = self.identify_opportunities(business, audit_report)

                ranked.append({
                    "business":           business,
                    "audit_report":       audit_report,
                    "quality_score":      quality,
                    "opportunity_score":  opportunity,
                    "priority_score":     priority,
                    "revenue_potential":  revenue,
                    "modernization_score": modernization,
                    "opportunities":      opportunities,
                })
            except Exception:
                # Never let a single bad record break the whole ranking.
                ranked.append({
                    "business":           business,
                    "audit_report":       audit_report,
                    "quality_score":      0.0,
                    "opportunity_score":  0.0,
                    "priority_score":     0.0,
                    "revenue_potential":  {"min": 0, "max": 0, "currency": "USD", "breakdown": {}},
                    "modernization_score": 0.0,
                    "opportunities":      [],
                })

        ranked.sort(key=lambda x: x["priority_score"], reverse=True)
        return ranked

    # ------------------------------------------------------------------ #
    # 7. Identify opportunities
    # ------------------------------------------------------------------ #

    def identify_opportunities(
        self,
        business: Any,
        audit_report: Any,
    ) -> List[Dict[str, Any]]:
        """
        Return a list of specific, actionable opportunity dicts.

        Each dict:
            {
                "type": str,           # redesign | seo | mobile | …
                "severity": str,       # critical | high | medium | low
                "title": str,
                "description": str,
                "estimated_value": float,  # USD midpoint
            }
        """
        opportunities: List[Dict[str, Any]] = []

        industry = (
            getattr(business, "industry", None) or
            getattr(business, "category", None)
        )
        city    = getattr(business, "city", None)
        country = getattr(business, "country", None)

        def _value(project_type: str) -> float:
            est = self._revenue_estimator.estimate_project_value(
                project_type, industry, city, country
            )
            return est["midpoint"]

        # No website at all.
        if not getattr(business, "has_website", True) or not getattr(audit_report, "website_url", None):
            opportunities.append({
                "type":            "new_website",
                "severity":        "critical",
                "title":           "No website detected",
                "description":     (
                    "This business has no web presence. A professional website "
                    "is the single highest-ROI digital investment available."
                ),
                "estimated_value": _value("new_website"),
            })
            return opportunities

        # Overall quality.
        quality = self.calculate_website_quality_score(audit_report)
        if quality < 35:
            opportunities.append({
                "type":            "redesign",
                "severity":        "critical",
                "title":           "Website requires complete redesign",
                "description":     (
                    f"Overall quality score is {quality:.0f}/100. The site has "
                    "severe deficiencies across multiple dimensions that a full "
                    "redesign would address."
                ),
                "estimated_value": _value("redesign"),
            })
        elif quality < 55:
            opportunities.append({
                "type":            "redesign",
                "severity":        "high",
                "title":           "Website significantly below industry standard",
                "description":     (
                    f"Quality score of {quality:.0f}/100 is well below the "
                    "recommended 70+ threshold. A redesign would materially "
                    "improve conversion rates and search rankings."
                ),
                "estimated_value": _value("redesign"),
            })
        elif quality < 70:
            opportunities.append({
                "type":            "redesign",
                "severity":        "medium",
                "title":           "Website improvements would boost performance",
                "description":     (
                    f"Score of {quality:.0f}/100 indicates meaningful gaps. "
                    "Targeted improvements to UI/UX and technical factors "
                    "would increase visitor engagement."
                ),
                "estimated_value": _value("redesign") * 0.6,
            })

        # SEO.
        seo = _safe_score(getattr(audit_report, "seo_score", None), default=50.0)
        seo_issues = getattr(audit_report, "seo_issues", None) or []
        if seo < 40:
            opportunities.append({
                "type":            "seo",
                "severity":        "critical",
                "title":           "Critical SEO deficiencies",
                "description":     (
                    f"SEO score of {seo:.0f}/100 with {len(seo_issues)} detected issues. "
                    "The site is largely invisible to search engines."
                ),
                "estimated_value": _value("seo"),
            })
        elif seo < 65:
            opportunities.append({
                "type":            "seo",
                "severity":        "high",
                "title":           "SEO improvements needed",
                "description":     (
                    f"SEO score of {seo:.0f}/100. Addressing technical and on-page "
                    "SEO issues could significantly increase organic traffic."
                ),
                "estimated_value": _value("seo"),
            })

        # Mobile.
        mobile = _safe_score(getattr(audit_report, "mobile_score", None), default=50.0)
        if mobile < 45:
            opportunities.append({
                "type":            "mobile",
                "severity":        "critical",
                "title":           "Site is not mobile-friendly",
                "description":     (
                    f"Mobile score of {mobile:.0f}/100. Over 60% of web traffic "
                    "is mobile; poor mobile UX directly hurts conversions and "
                    "Google rankings."
                ),
                "estimated_value": _value("mobile_optimization"),
            })
        elif mobile < 65:
            opportunities.append({
                "type":            "mobile",
                "severity":        "high",
                "title":           "Mobile experience needs improvement",
                "description":     (
                    f"Mobile score of {mobile:.0f}/100 indicates a sub-par "
                    "experience on smartphones and tablets."
                ),
                "estimated_value": _value("mobile_optimization"),
            })

        # Accessibility.
        acc = _safe_score(getattr(audit_report, "accessibility_score", None), default=50.0)
        acc_issues = getattr(audit_report, "accessibility_issues", None) or []
        critical_acc = [
            i for i in acc_issues
            if str(i.get("impact", "")).lower() in ("critical", "serious")
        ]
        if acc < 50 or critical_acc:
            severity = "critical" if critical_acc else "high"
            opportunities.append({
                "type":            "accessibility",
                "severity":        severity,
                "title":           "Accessibility violations present",
                "description":     (
                    f"Accessibility score {acc:.0f}/100 with "
                    f"{len(critical_acc)} critical/serious violations. "
                    "Legal liability and loss of users with disabilities."
                ),
                "estimated_value": _value("accessibility"),
            })

        # Performance.
        perf = _safe_score(getattr(audit_report, "speed_score", None), default=50.0)
        perf_metrics: Optional[Dict] = getattr(audit_report, "performance_metrics", None)
        lcp = float((perf_metrics or {}).get("lcp", 0) or 0)
        if perf < 45 or lcp > 4.0:
            opportunities.append({
                "type":            "performance",
                "severity":        "high",
                "title":           "Slow page load speeds hurting conversions",
                "description":     (
                    f"Performance score {perf:.0f}/100"
                    + (f", LCP {lcp:.1f}s" if lcp else "") +
                    ". Each second of delay reduces conversions by ~7%."
                ),
                "estimated_value": _value("performance"),
            })
        elif perf < 65:
            opportunities.append({
                "type":            "performance",
                "severity":        "medium",
                "title":           "Page speed optimisation opportunity",
                "description":     (
                    f"Performance score {perf:.0f}/100. Targeted optimisations "
                    "to images, caching, and scripts would improve Core Web Vitals."
                ),
                "estimated_value": _value("performance") * 0.6,
            })

        # Security.
        sec = _safe_score(getattr(audit_report, "security_score", None), default=50.0)
        if sec < 50:
            opportunities.append({
                "type":            "security",
                "severity":        "high",
                "title":           "Security vulnerabilities detected",
                "description":     (
                    f"Security score {sec:.0f}/100. Missing security headers, "
                    "HTTPS issues, or outdated software put the business at risk."
                ),
                "estimated_value": _value("security_hardening"),
            })

        # Branding / content.
        brand = _safe_score(getattr(audit_report, "branding_score", None), default=50.0)
        if brand < 45:
            opportunities.append({
                "type":            "branding",
                "severity":        "medium",
                "title":           "Weak or inconsistent brand presence",
                "description":     (
                    f"Branding score {brand:.0f}/100. Inconsistent visual identity "
                    "erodes trust and reduces recall."
                ),
                "estimated_value": _value("branding"),
            })

        content = _safe_score(getattr(audit_report, "content_score", None), default=50.0)
        if content < 45:
            opportunities.append({
                "type":            "content",
                "severity":        "medium",
                "title":           "Content quality and structure improvements needed",
                "description":     (
                    f"Content score {content:.0f}/100. Clearer copy and stronger "
                    "calls-to-action would improve engagement and conversions."
                ),
                "estimated_value": _value("content_rewrite"),
            })

        # Modernization — outdated look/tech.
        mod = self.calculate_modernization_score(audit_report)
        if mod < 35:
            opportunities.append({
                "type":            "modernization",
                "severity":        "high",
                "title":           "Website looks outdated",
                "description":     (
                    f"Modernization score {mod:.0f}/100. The site uses legacy "
                    "technologies or design patterns that signal an old, "
                    "untrustworthy brand to visitors."
                ),
                "estimated_value": _value("redesign") * 0.8,
            })

        # Sort by severity.
        _severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        opportunities.sort(key=lambda x: _severity_order.get(x["severity"], 9))

        return opportunities
