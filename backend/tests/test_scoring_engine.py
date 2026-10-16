"""
Unit tests for ScoringEngine and RevenueEstimator.

All tests operate on plain Python objects (no DB, no async).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from app.engines.scoring.revenue_estimator import RevenueEstimator
from app.engines.scoring.scoring_engine import ScoreWeights, ScoringEngine


# ---------------------------------------------------------------------------
# Helpers — lightweight duck-typed Business / AuditReport substitutes
# ---------------------------------------------------------------------------


@dataclass
class _FakeBusiness:
    name: str = "Test Business"
    industry: Optional[str] = None
    category: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    has_website: bool = True
    social_profiles: Optional[Dict[str, Any]] = None


@dataclass
class _FakeAudit:
    website_url: Optional[str] = "https://example.com"
    ui_score: Optional[float] = None
    ux_score: Optional[float] = None
    mobile_score: Optional[float] = None
    seo_score: Optional[float] = None
    accessibility_score: Optional[float] = None
    speed_score: Optional[float] = None
    security_score: Optional[float] = None
    branding_score: Optional[float] = None
    content_score: Optional[float] = None
    conversion_score: Optional[float] = None
    seo_issues: Optional[List[Dict[str, Any]]] = None
    accessibility_issues: Optional[List[Dict[str, Any]]] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    tech_stack: Optional[List[Dict[str, Any]]] = None


# ---------------------------------------------------------------------------
# ScoreWeights validation
# ---------------------------------------------------------------------------


def test_score_weights_default_sum_to_one() -> None:
    """Default ScoreWeights values must sum to 1.0."""
    import math

    w = ScoreWeights()
    total = (
        w.ui + w.ux + w.mobile + w.seo
        + w.accessibility + w.performance + w.security
        + w.branding + w.content + w.conversion
    )
    assert math.isclose(total, 1.0, rel_tol=1e-4)


def test_score_weights_invalid_raises() -> None:
    """Weights that don't sum to 1.0 raise ValueError."""
    with pytest.raises(ValueError, match="sum to 1.0"):
        ScoreWeights(ui=0.99)  # all others default → total >> 1.0


# ---------------------------------------------------------------------------
# Website quality score
# ---------------------------------------------------------------------------


def test_website_quality_score_all_100() -> None:
    """An audit where every sub-score is 100 yields 100.0."""
    engine = ScoringEngine()
    audit = _FakeAudit(
        ui_score=100, ux_score=100, mobile_score=100, seo_score=100,
        accessibility_score=100, speed_score=100, security_score=100,
        branding_score=100, content_score=100, conversion_score=100,
    )
    score = engine.calculate_website_quality_score(audit)
    assert score == 100.0


def test_website_quality_score_all_zero() -> None:
    """An audit where every sub-score is 0 yields 0.0."""
    engine = ScoringEngine()
    audit = _FakeAudit(
        ui_score=0, ux_score=0, mobile_score=0, seo_score=0,
        accessibility_score=0, speed_score=0, security_score=0,
        branding_score=0, content_score=0, conversion_score=0,
    )
    score = engine.calculate_website_quality_score(audit)
    assert score == 0.0


def test_website_quality_score_missing_defaults_to_50() -> None:
    """Missing sub-scores default to 50 (neutral), not 0."""
    engine = ScoringEngine()
    audit = _FakeAudit()  # all scores are None
    score = engine.calculate_website_quality_score(audit)
    assert score == pytest.approx(50.0, abs=0.1)


def test_website_quality_score_calculation_partial() -> None:
    """Explicit sub-scores produce a deterministic weighted result."""
    engine = ScoringEngine()
    # Only SEO is poor (30), everything else absent (defaults to 50)
    audit = _FakeAudit(seo_score=30.0)
    score = engine.calculate_website_quality_score(audit)
    # SEO weight is 0.15; delta from 50 is (30-50)*0.15 = -3.0
    assert score < 50.0
    assert score == pytest.approx(50.0 - 3.0, abs=0.1)


# ---------------------------------------------------------------------------
# Opportunity score
# ---------------------------------------------------------------------------


def test_opportunity_score_high_for_no_website() -> None:
    """A business with no website and a poor audit has a high opportunity score."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=False, industry="restaurant")
    audit = _FakeAudit(website_url=None, ui_score=0, ux_score=0, seo_score=0)
    score = engine.calculate_opportunity_score(business, audit)
    assert score >= 50.0, f"Expected high opportunity score, got {score}"


def test_opportunity_score_low_for_excellent_site() -> None:
    """A perfect website offers little opportunity."""
    engine = ScoringEngine()
    business = _FakeBusiness(industry="salon")
    audit = _FakeAudit(
        ui_score=100, ux_score=100, mobile_score=100, seo_score=100,
        accessibility_score=100, speed_score=100, security_score=100,
        branding_score=100, content_score=100, conversion_score=100,
    )
    score = engine.calculate_opportunity_score(business, audit)
    assert score < 50.0, f"Expected low opportunity score, got {score}"


def test_opportunity_score_in_range() -> None:
    """Opportunity score is always in [0, 100]."""
    engine = ScoringEngine()
    business = _FakeBusiness(industry="legal", city="New York", country="US")
    audit = _FakeAudit(seo_score=10, mobile_score=15, speed_score=20)
    score = engine.calculate_opportunity_score(business, audit)
    assert 0.0 <= score <= 100.0


def test_opportunity_score_high_value_industry_boosts_score() -> None:
    """A legal firm (high-value industry) gets a higher score than a bakery."""
    engine = ScoringEngine()
    audit = _FakeAudit()  # neutral

    legal = _FakeBusiness(industry="legal")
    bakery = _FakeBusiness(industry="bakery")

    legal_score = engine.calculate_opportunity_score(legal, audit)
    bakery_score = engine.calculate_opportunity_score(bakery, audit)
    assert legal_score > bakery_score


# ---------------------------------------------------------------------------
# Revenue estimate ranges
# ---------------------------------------------------------------------------


def test_revenue_estimate_ranges_no_website() -> None:
    """A business with no website should be estimated for a new_website project."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=False, industry="restaurant", country="US")
    audit = _FakeAudit(website_url=None)
    result = engine.estimate_revenue_potential(business, audit)
    assert result["min"] > 0
    assert result["max"] > result["min"]
    assert result["currency"] == "USD"
    # Breakdown must contain new_website
    assert "new_website" in result["breakdown"]


def test_revenue_estimate_ranges_poor_site() -> None:
    """A poor-quality site should include redesign in the estimate."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="plumbing", country="US")
    audit = _FakeAudit(
        ui_score=20, ux_score=25, seo_score=15, mobile_score=10,
    )
    result = engine.estimate_revenue_potential(business, audit)
    assert result["min"] > 0
    assert "redesign" in result["breakdown"]


def test_revenue_estimate_maintenance_always_included() -> None:
    """maintenance_monthly is always included regardless of site quality."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="technology", country="US")
    audit = _FakeAudit(
        ui_score=90, ux_score=90, seo_score=90, mobile_score=90,
    )
    result = engine.estimate_revenue_potential(business, audit)
    assert "maintenance_monthly" in result["breakdown"]


def test_revenue_estimate_high_value_city_premium() -> None:
    """Projects in NYC cost more than the same project in a small city."""
    estimator = RevenueEstimator()
    nyc = estimator.estimate_project_value("redesign", industry="legal", city="New York", country="US")
    rural = estimator.estimate_project_value("redesign", industry="legal", city=None, country="US")
    assert nyc["min"] > rural["min"]


def test_revenue_estimate_industry_multiplier_applied() -> None:
    """Legal industry multiplier produces higher values than default."""
    estimator = RevenueEstimator()
    legal = estimator.estimate_project_value("new_website", industry="legal")
    default = estimator.estimate_project_value("new_website", industry=None)
    assert legal["min"] > default["min"]


def test_revenue_estimate_unknown_project_type_fallback() -> None:
    """An unknown project type falls back to redesign pricing."""
    estimator = RevenueEstimator()
    result = estimator.estimate_project_value("totally_unknown_project")
    redesign = estimator.estimate_project_value("redesign")
    assert result["min"] == redesign["min"]


# ---------------------------------------------------------------------------
# Opportunity identification
# ---------------------------------------------------------------------------


def test_opportunity_identification_no_website() -> None:
    """Business with no website should surface a 'new_website' opportunity."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=False)
    audit = _FakeAudit(website_url=None)
    opps = engine.identify_opportunities(business, audit)
    types = [o["type"] for o in opps]
    assert "new_website" in types
    # No other opportunities when there's no website to analyse
    assert len(opps) == 1


def test_opportunity_identification_poor_seo() -> None:
    """Poor SEO score surfaces an SEO opportunity."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="restaurant")
    audit = _FakeAudit(seo_score=20.0)
    opps = engine.identify_opportunities(business, audit)
    types = [o["type"] for o in opps]
    assert "seo" in types


def test_opportunity_identification_sorted_by_severity() -> None:
    """Opportunities are sorted critical → high → medium → low."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="legal")
    audit = _FakeAudit(
        seo_score=10,       # critical SEO
        mobile_score=30,    # critical mobile
        branding_score=20,  # medium branding
    )
    opps = engine.identify_opportunities(business, audit)
    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    severities = [_order.get(o["severity"], 9) for o in opps]
    assert severities == sorted(severities), "Opportunities are not sorted by severity"


def test_opportunity_identification_all_scores_high() -> None:
    """A business with all high scores has few or no opportunities."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="technology")
    audit = _FakeAudit(
        ui_score=90, ux_score=90, mobile_score=90, seo_score=90,
        accessibility_score=90, speed_score=90, security_score=90,
        branding_score=90, content_score=90, conversion_score=90,
    )
    opps = engine.identify_opportunities(business, audit)
    assert len(opps) == 0


def test_opportunity_estimated_value_is_positive() -> None:
    """Every identified opportunity has a positive estimated_value."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="construction", country="US")
    audit = _FakeAudit(
        seo_score=15,
        mobile_score=20,
        speed_score=25,
        accessibility_score=10,
        accessibility_issues=[{"rule": "color-contrast", "impact": "serious"}],
    )
    opps = engine.identify_opportunities(business, audit)
    for opp in opps:
        assert opp["estimated_value"] > 0, f"Zero value for {opp['type']}"


# ---------------------------------------------------------------------------
# Priority score
# ---------------------------------------------------------------------------


def test_priority_score_range() -> None:
    """Priority score is always in [0, 100]."""
    engine = ScoringEngine()
    business = _FakeBusiness(has_website=True, industry="legal", city="Austin", country="US")
    audit = _FakeAudit(seo_score=30, mobile_score=25)
    score = engine.calculate_priority_score(business, audit)
    assert 0.0 <= score <= 100.0


def test_rank_businesses_sorted_descending() -> None:
    """rank_businesses returns businesses sorted by priority_score descending."""
    engine = ScoringEngine()

    poor_biz = _FakeBusiness(name="Poor Site", has_website=True, industry="plumbing")
    poor_audit = _FakeAudit(
        seo_score=10, mobile_score=5, ui_score=10, accessibility_score=5,
    )

    good_biz = _FakeBusiness(name="Good Site", has_website=True, industry="plumbing")
    good_audit = _FakeAudit(
        seo_score=90, mobile_score=90, ui_score=90, accessibility_score=90,
    )

    ranked = engine.rank_businesses([(poor_biz, poor_audit), (good_biz, good_audit)])
    assert len(ranked) == 2
    # Poor site has more opportunity so should be ranked first
    assert ranked[0]["priority_score"] >= ranked[1]["priority_score"]


def test_rank_businesses_handles_empty_list() -> None:
    """rank_businesses on an empty list returns an empty list."""
    engine = ScoringEngine()
    assert engine.rank_businesses([]) == []
