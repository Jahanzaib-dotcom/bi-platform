"""
AI Analyzer — Claude-powered website analysis engine.

Uses the ``anthropic`` SDK (AsyncAnthropic) to call claude-opus-4-8 and produce
a rich, structured analysis of a business's web presence.  Falls back to
rule-based heuristics when no Anthropic API key is configured.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class VisualAnalysis:
    """Results from screenshot / visual analysis via Claude Vision."""

    design_style: str = "unknown"
    color_scheme: List[str] = field(default_factory=list)
    layout_type: str = "unknown"          # e.g. "single-page", "multi-column"
    cta_visible: bool = False
    mobile_friendly_visual: bool = False
    visual_quality_score: float = 50.0    # 0–100
    professionalism_score: float = 50.0   # 0–100
    issues_detected: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    raw_description: str = ""


@dataclass
class AIAnalysis:
    """
    Structured AI analysis of a business website.

    All list fields contain plain-language strings that can be surfaced directly
    to an end user or salesperson.
    """

    # Visual / design quality (0–100)
    design_quality_score: float = 50.0
    modernity_score: float = 50.0
    professionalism_score: float = 50.0
    brand_consistency_score: float = 50.0
    conversion_quality_score: float = 50.0

    # Qualitative summary
    overall_impression: str = ""

    # Opportunity lists
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    quick_wins: List[str] = field(default_factory=list)
    redesign_opportunities: List[str] = field(default_factory=list)
    ai_opportunities: List[str] = field(default_factory=list)
    automation_opportunities: List[str] = field(default_factory=list)

    # Business value
    estimated_project_value: Dict[str, Any] = field(default_factory=dict)

    # Competitive context
    competitor_analysis_notes: str = ""

    # Sales / priority
    priority_recommendation: str = ""

    # Optional raw model output for debugging
    raw_response: Optional[str] = None


# ---------------------------------------------------------------------------
# AIAnalyzer
# ---------------------------------------------------------------------------


class AIAnalyzer:
    """
    Generates AI-powered analysis of business websites.

    Usage::

        analyzer = AIAnalyzer()
        result: AIAnalysis = await analyzer.analyze_website(business, audit_report)
        visual: VisualAnalysis = await analyzer.analyze_screenshot(screenshot_bytes)
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        # Resolve API key: explicit argument > settings
        from app.core.config import settings

        self._api_key: str = api_key or settings.ANTHROPIC_API_KEY or ""
        self._model: str = model or settings.AI_MODEL or "claude-opus-4-8"
        self._client: Any = None  # lazily initialised AsyncAnthropic

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_client(self) -> Any:
        """Return (and lazily create) the AsyncAnthropic client."""
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("No Anthropic API key configured.")
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _safe_score(value: Any, default: float = 50.0) -> float:
        """Clamp an optional numeric value to [0, 100]."""
        if value is None:
            return default
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _get(obj: Any, attr: str, default: Any = None) -> Any:
        """Attribute or dict key access with fallback."""
        if isinstance(obj, dict):
            return obj.get(attr, default)
        return getattr(obj, attr, default)

    # ------------------------------------------------------------------ #
    # Prompt builder
    # ------------------------------------------------------------------ #

    def _build_analysis_prompt(self, business: Any, audit_report: Any) -> str:
        """Construct a rich prompt from audit and business data."""

        def g(obj: Any, attr: str, default: Any = None) -> Any:
            return self._get(obj, attr, default)

        name = g(business, "name", "Unknown Business")
        industry = g(business, "industry", "Unknown")
        category = g(business, "category", "")
        city = g(business, "city", "")
        country = g(business, "country", "")
        website_url = g(audit_report, "website_url", "") or g(business, "website_url", "")

        scores = {
            "UI":           self._safe_score(g(audit_report, "ui_score")),
            "UX":           self._safe_score(g(audit_report, "ux_score")),
            "Mobile":       self._safe_score(g(audit_report, "mobile_score")),
            "SEO":          self._safe_score(g(audit_report, "seo_score")),
            "Accessibility": self._safe_score(g(audit_report, "accessibility_score")),
            "Speed":        self._safe_score(g(audit_report, "speed_score")),
            "Security":     self._safe_score(g(audit_report, "security_score")),
            "Branding":     self._safe_score(g(audit_report, "branding_score")),
            "Content":      self._safe_score(g(audit_report, "content_score")),
            "Conversion":   self._safe_score(g(audit_report, "conversion_score")),
            "Overall":      self._safe_score(g(audit_report, "overall_score")),
        }

        seo_issues = g(audit_report, "seo_issues") or []
        a11y_issues = g(audit_report, "accessibility_issues") or []
        perf_metrics = g(audit_report, "performance_metrics") or {}
        tech_stack = g(audit_report, "tech_stack") or []
        recommendations = g(audit_report, "recommendations") or []

        # Format scores table
        score_lines = "\n".join(
            f"  {k:15s}: {v:.1f}/100" for k, v in scores.items()
        )

        # Summarise issue counts
        seo_critical = sum(
            1 for i in seo_issues if isinstance(i, dict) and i.get("severity") in ("critical", "high")
        )
        a11y_critical = sum(
            1 for i in a11y_issues if isinstance(i, dict) and i.get("impact") in ("critical", "serious")
        )

        # Tech stack summary
        tech_names = ", ".join(
            t.get("name", str(t)) if isinstance(t, dict) else str(t)
            for t in tech_stack[:10]
        ) or "Not detected"

        # Performance highlights
        lcp = perf_metrics.get("lcp", "N/A")
        cls_ = perf_metrics.get("cls", "N/A")
        ttfb = perf_metrics.get("ttfb", "N/A")

        # Top recommendations snippet
        rec_lines = "\n".join(
            f"  - [{r.get('priority','?').upper()}] {r.get('title', '')}: {r.get('description', '')}"
            for r in recommendations[:5]
            if isinstance(r, dict)
        ) or "  None captured."

        prompt = f"""You are a senior digital strategist and web development expert. Analyse the following business website audit data and produce a structured JSON assessment.

## Business Details
- Name: {name}
- Industry: {industry}
- Category: {category}
- Location: {city}, {country}
- Website: {website_url}

## Audit Scores (0–100, higher = better)
{score_lines}

## Issues Found
- SEO issues (critical/high): {seo_critical} of {len(seo_issues)} total
- Accessibility issues (critical/serious): {a11y_critical} of {len(a11y_issues)} total

## Performance Metrics
- LCP: {lcp}
- CLS: {cls_}
- TTFB: {ttfb}

## Technology Stack
{tech_names}

## Top Recommendations
{rec_lines}

---

Based on the above data, return a JSON object with **exactly** these keys:

{{
  "design_quality_score": <float 0-100>,
  "modernity_score": <float 0-100>,
  "professionalism_score": <float 0-100>,
  "brand_consistency_score": <float 0-100>,
  "conversion_quality_score": <float 0-100>,
  "overall_impression": "<2-3 sentence summary of the site's current state>",
  "strengths": ["<strength 1>", ...],
  "weaknesses": ["<weakness 1>", ...],
  "quick_wins": ["<quick win 1>", ...],
  "redesign_opportunities": ["<opportunity 1>", ...],
  "ai_opportunities": ["<AI/ML enhancement idea 1>", ...],
  "automation_opportunities": ["<automation idea 1>", ...],
  "estimated_project_value": {{
    "min": <USD amount>,
    "max": <USD amount>,
    "primary_project": "<project type>",
    "rationale": "<1-2 sentences>"
  }},
  "competitor_analysis_notes": "<brief notes on competitive positioning>",
  "priority_recommendation": "<1-2 sentence sales recommendation>"
}}

Respond with ONLY the JSON object — no markdown fences, no prose before or after.
"""
        return prompt

    # ------------------------------------------------------------------ #
    # Public async API
    # ------------------------------------------------------------------ #

    async def analyze_website(
        self,
        business: Any,
        audit_report: Any,
        screenshot_path: Optional[str] = None,
    ) -> AIAnalysis:
        """
        Produce a full AIAnalysis for the given business / audit pair.

        Falls back to rule-based analysis when no API key is configured or
        when the Claude API call fails.
        """
        if not self._api_key:
            logger.info("No Anthropic API key — using rule-based analysis fallback.")
            return self._generate_rule_based_analysis(business, audit_report)

        try:
            return await self._analyze_with_claude(business, audit_report, screenshot_path)
        except Exception as exc:
            logger.warning("Claude API call failed (%s); falling back to rule-based analysis.", exc)
            return self._generate_rule_based_analysis(business, audit_report)

    async def _analyze_with_claude(
        self,
        business: Any,
        audit_report: Any,
        screenshot_path: Optional[str] = None,
    ) -> AIAnalysis:
        """Call Claude and parse the structured JSON response."""
        client = self._get_client()

        prompt_text = self._build_analysis_prompt(business, audit_report)

        # Build the message content
        content: List[Any] = [{"type": "text", "text": prompt_text}]

        # Optionally attach a screenshot for visual grounding
        if screenshot_path:
            try:
                image_data = Path(screenshot_path).read_bytes()
                b64 = base64.standard_b64encode(image_data).decode()
                content.insert(
                    0,
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                )
            except Exception as exc:
                logger.warning("Could not load screenshot %s: %s", screenshot_path, exc)

        response = await client.messages.create(
            model=self._model,
            max_tokens=2048,
            messages=[{"role": "user", "content": content}],
        )

        raw_text: str = response.content[0].text if response.content else ""
        return self._parse_ai_response(raw_text)

    def _parse_ai_response(self, raw_text: str) -> AIAnalysis:
        """Parse Claude's JSON response into an AIAnalysis dataclass."""
        # Strip markdown fences if present
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data: Dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse AI response JSON: %s\nRaw: %s", exc, raw_text[:500])
            return AIAnalysis(raw_response=raw_text)

        ev = data.get("estimated_project_value", {})
        if not isinstance(ev, dict):
            ev = {}

        return AIAnalysis(
            design_quality_score=self._safe_score(data.get("design_quality_score")),
            modernity_score=self._safe_score(data.get("modernity_score")),
            professionalism_score=self._safe_score(data.get("professionalism_score")),
            brand_consistency_score=self._safe_score(data.get("brand_consistency_score")),
            conversion_quality_score=self._safe_score(data.get("conversion_quality_score")),
            overall_impression=str(data.get("overall_impression", "")),
            strengths=list(data.get("strengths") or []),
            weaknesses=list(data.get("weaknesses") or []),
            quick_wins=list(data.get("quick_wins") or []),
            redesign_opportunities=list(data.get("redesign_opportunities") or []),
            ai_opportunities=list(data.get("ai_opportunities") or []),
            automation_opportunities=list(data.get("automation_opportunities") or []),
            estimated_project_value=ev,
            competitor_analysis_notes=str(data.get("competitor_analysis_notes", "")),
            priority_recommendation=str(data.get("priority_recommendation", "")),
            raw_response=None,  # Don't store raw when parse succeeds
        )

    async def analyze_screenshot(self, screenshot_bytes: bytes) -> VisualAnalysis:
        """
        Use Claude Vision to analyse a raw screenshot and return a VisualAnalysis.

        Falls back to a minimal default when the API key is missing or the call
        fails.
        """
        if not self._api_key:
            logger.info("No Anthropic API key — returning default VisualAnalysis.")
            return VisualAnalysis()

        try:
            return await self._analyze_screenshot_with_claude(screenshot_bytes)
        except Exception as exc:
            logger.warning("Screenshot analysis failed (%s); returning default.", exc)
            return VisualAnalysis()

    async def _analyze_screenshot_with_claude(
        self, screenshot_bytes: bytes
    ) -> VisualAnalysis:
        """Send a screenshot to Claude Vision and parse the response."""
        client = self._get_client()

        b64 = base64.standard_b64encode(screenshot_bytes).decode()

        vision_prompt = (
            "Analyse this website screenshot and return a JSON object with exactly these keys:\n\n"
            '{"design_style": "<e.g. minimal, corporate, playful, dark, light>",\n'
            ' "color_scheme": ["<color 1>", ...],\n'
            ' "layout_type": "<e.g. single-column, multi-column, hero-centric, grid>",\n'
            ' "cta_visible": <true|false>,\n'
            ' "mobile_friendly_visual": <true|false>,\n'
            ' "visual_quality_score": <float 0-100>,\n'
            ' "professionalism_score": <float 0-100>,\n'
            ' "issues_detected": ["<issue 1>", ...],\n'
            ' "recommendations": ["<recommendation 1>", ...],\n'
            ' "raw_description": "<2-3 sentence description of what you see>"}\n\n'
            "Return ONLY the JSON — no markdown fences, no prose."
        )

        response = await client.messages.create(
            model=self._model,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": vision_prompt},
                    ],
                }
            ],
        )

        raw_text = response.content[0].text if response.content else ""
        return self._parse_visual_response(raw_text)

    def _parse_visual_response(self, raw_text: str) -> VisualAnalysis:
        """Parse Claude's JSON into a VisualAnalysis dataclass."""
        cleaned = raw_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            data: Dict[str, Any] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse visual response JSON: %s", exc)
            return VisualAnalysis(raw_description=raw_text)

        return VisualAnalysis(
            design_style=str(data.get("design_style", "unknown")),
            color_scheme=list(data.get("color_scheme") or []),
            layout_type=str(data.get("layout_type", "unknown")),
            cta_visible=bool(data.get("cta_visible", False)),
            mobile_friendly_visual=bool(data.get("mobile_friendly_visual", False)),
            visual_quality_score=self._safe_score(data.get("visual_quality_score")),
            professionalism_score=self._safe_score(data.get("professionalism_score")),
            issues_detected=list(data.get("issues_detected") or []),
            recommendations=list(data.get("recommendations") or []),
            raw_description=str(data.get("raw_description", "")),
        )

    # ------------------------------------------------------------------ #
    # Rule-based fallback
    # ------------------------------------------------------------------ #

    def _generate_rule_based_analysis(
        self, business: Any, audit_report: Any
    ) -> AIAnalysis:
        """
        Produce a deterministic AIAnalysis from audit scores alone.

        Used when no Anthropic API key is available or when the API fails.
        """

        def g(obj: Any, attr: str, default: Any = None) -> Any:
            return self._get(obj, attr, default)

        s = self._safe_score

        ui = s(g(audit_report, "ui_score"))
        ux = s(g(audit_report, "ux_score"))
        mobile = s(g(audit_report, "mobile_score"))
        seo = s(g(audit_report, "seo_score"))
        a11y = s(g(audit_report, "accessibility_score"))
        speed = s(g(audit_report, "speed_score"))
        security = s(g(audit_report, "security_score"))
        branding = s(g(audit_report, "branding_score"))
        content = s(g(audit_report, "content_score"))
        conversion = s(g(audit_report, "conversion_score"))
        overall = s(g(audit_report, "overall_score"))

        industry = str(g(business, "industry", "") or "").lower()
        name = g(business, "name", "the business")
        city = str(g(business, "city", "") or "")
        country = str(g(business, "country", "") or "")
        location = ", ".join(filter(None, [city, country])) or "your area"

        # Derived composite scores
        design_quality = (ui * 0.5 + branding * 0.5)
        modernity = (ui * 0.4 + speed * 0.3 + mobile * 0.3)
        professionalism = (branding * 0.4 + content * 0.3 + ui * 0.3)
        brand_consistency = branding
        conversion_quality = conversion

        # Overall impression
        if overall >= 75:
            impression = (
                f"{name} has a solid web presence with scores above average across most dimensions. "
                "There are still targeted improvements that could meaningfully increase leads and conversions. "
                "Presenting a refined digital strategy would likely resonate well."
            )
        elif overall >= 50:
            impression = (
                f"{name} has a functional website but falls short in several key areas. "
                "Improvements to SEO, performance, and conversion paths represent immediate revenue opportunities. "
                "A focused engagement could yield strong ROI."
            )
        else:
            impression = (
                f"{name}'s website is significantly underperforming, creating an urgent competitive disadvantage. "
                "Visitors are likely bouncing due to poor speed, mobile experience, or lack of trust signals. "
                "This business is a high-priority prospect for a comprehensive digital overhaul."
            )

        # --- Strengths ---
        strengths: List[str] = []
        if ui >= 70:
            strengths.append("Clean, visually appealing user interface")
        if ux >= 70:
            strengths.append("Intuitive user experience and clear navigation")
        if mobile >= 70:
            strengths.append("Good mobile responsiveness")
        if seo >= 70:
            strengths.append("Solid on-page SEO foundations")
        if security >= 70:
            strengths.append("HTTPS and basic security practices in place")
        if speed >= 70:
            strengths.append("Fast page load times")
        if content >= 70:
            strengths.append("Quality content that communicates value effectively")
        if not strengths:
            strengths.append("Website is live and indexed by search engines")

        # --- Weaknesses ---
        weaknesses: List[str] = []
        if mobile < 60:
            weaknesses.append(f"Poor mobile experience (score: {mobile:.0f}/100) — ~60% of traffic is mobile")
        if seo < 60:
            weaknesses.append(f"Weak SEO foundations (score: {seo:.0f}/100) limiting organic reach")
        if speed < 60:
            weaknesses.append(f"Slow page load speed (score: {speed:.0f}/100) increasing bounce rates")
        if a11y < 60:
            weaknesses.append(f"Accessibility gaps (score: {a11y:.0f}/100) excluding potential customers")
        if conversion < 60:
            weaknesses.append(f"Weak conversion elements (score: {conversion:.0f}/100) — calls-to-action need work")
        if security < 60:
            weaknesses.append(f"Security concerns (score: {security:.0f}/100) that may deter visitors")
        if branding < 60:
            weaknesses.append("Inconsistent branding reducing trust and memorability")
        if content < 60:
            weaknesses.append("Thin or unfocused content not aligned with search intent")
        if not weaknesses:
            weaknesses.append("Minor refinements possible but no critical issues detected")

        # --- Quick wins ---
        quick_wins: List[str] = []
        if seo < 70:
            quick_wins.append("Add meta descriptions and title tags to all pages (1–2 hours of work)")
        if mobile < 70:
            quick_wins.append("Fix viewport meta tag and ensure tap targets meet 44×44 px minimum")
        if speed < 70:
            quick_wins.append("Compress and lazy-load images to cut page weight by 30–50%")
        if a11y < 70:
            quick_wins.append("Add alt text to all images and fix heading hierarchy")
        if conversion < 70:
            quick_wins.append("Add a prominent above-the-fold CTA button with a clear value proposition")
        if security < 70:
            quick_wins.append("Install/renew SSL certificate and redirect all HTTP to HTTPS")
        if not quick_wins:
            quick_wins.append("Conduct a full UX audit to surface hidden friction points")

        # --- Redesign opportunities ---
        redesign_opps: List[str] = []
        if ui < 65 or ux < 65:
            redesign_opps.append("Complete UI/UX redesign to modernise look and improve conversion flow")
        if mobile < 60:
            redesign_opps.append("Mobile-first redesign to capture the majority of web traffic")
        if branding < 60:
            redesign_opps.append("Brand identity refresh including typography, colour palette, and logo usage")
        if "ecommerce" in industry or "retail" in industry or "shop" in industry:
            redesign_opps.append("E-commerce upgrade with product filtering, reviews, and streamlined checkout")
        if not redesign_opps:
            redesign_opps.append("Incremental design polish rather than a full overhaul at this stage")

        # --- AI opportunities ---
        ai_opps: List[str] = [
            f"AI-powered chatbot to handle FAQs and qualify leads for {name} 24/7",
            "Personalised content recommendations based on visitor behaviour",
            "AI-driven SEO content generation to accelerate organic growth",
        ]
        if "legal" in industry or "consulting" in industry or "finance" in industry:
            ai_opps.append("AI document analysis and client intake automation")
        if "ecommerce" in industry or "retail" in industry:
            ai_opps.append("AI product recommendations and dynamic pricing engine")
        if "healthcare" in industry or "medical" in industry:
            ai_opps.append("AI symptom checker or appointment scheduling assistant")

        # --- Automation opportunities ---
        automation_opps: List[str] = [
            "Automated lead follow-up email sequences triggered by form submissions",
            "CRM integration to capture and score leads automatically",
            f"Google Business Profile auto-posting to boost local visibility in {location}",
        ]
        if "restaurant" in industry or "food" in industry or "hospitality" in industry:
            automation_opps.append("Online booking / reservation automation with confirmation emails")
        if "ecommerce" in industry or "retail" in industry:
            automation_opps.append("Abandoned cart recovery emails and post-purchase review requests")

        # --- Revenue estimate (simple rule-based) ---
        base_project = "redesign"
        base_value_min = 3_000.0
        base_value_max = 20_000.0

        # Industry multiplier approximation
        high_value = ("legal", "finance", "healthcare", "real_estate", "insurance", "technology")
        multiplier = 1.6 if any(h in industry for h in high_value) else 1.0

        estimated_project_value = {
            "min": round(base_value_min * multiplier, 2),
            "max": round(base_value_max * multiplier, 2),
            "primary_project": base_project,
            "rationale": (
                f"Based on a {industry or 'general'} business in {location} with an overall score "
                f"of {overall:.0f}/100. A full redesign with SEO and performance work is the "
                "recommended entry-point engagement."
            ),
        }

        # --- Competitor analysis notes ---
        competitor_notes = (
            f"Businesses in the {industry or 'same'} sector in {location} are increasingly investing "
            "in mobile-optimised, conversion-focused websites. Without improvements, "
            f"{name} risks losing ground to more digitally mature competitors."
        )

        # --- Priority recommendation ---
        if overall < 50:
            priority_rec = (
                f"HIGH PRIORITY — {name} has significant digital gaps that are actively costing them customers. "
                "Propose a phased engagement starting with a quick-win audit, then a full redesign."
            )
        elif overall < 70:
            priority_rec = (
                f"MEDIUM PRIORITY — {name} has a functional presence but clear room for improvement. "
                "A targeted SEO + conversion optimisation package would deliver fast, measurable ROI."
            )
        else:
            priority_rec = (
                f"LOWER PRIORITY — {name}'s website is reasonably solid. "
                "Focus on advanced SEO, content marketing, or AI-powered features as upsell opportunities."
            )

        return AIAnalysis(
            design_quality_score=round(design_quality, 1),
            modernity_score=round(modernity, 1),
            professionalism_score=round(professionalism, 1),
            brand_consistency_score=round(brand_consistency, 1),
            conversion_quality_score=round(conversion_quality, 1),
            overall_impression=impression,
            strengths=strengths,
            weaknesses=weaknesses,
            quick_wins=quick_wins,
            redesign_opportunities=redesign_opps,
            ai_opportunities=ai_opps,
            automation_opportunities=automation_opps,
            estimated_project_value=estimated_project_value,
            competitor_analysis_notes=competitor_notes,
            priority_recommendation=priority_rec,
        )
