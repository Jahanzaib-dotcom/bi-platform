from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

SERVICE_PRICING: dict[str, dict[str, Any]] = {
    "website_redesign": {"name": "Website Redesign", "min": 499, "max": 1499},
    "seo_optimization": {"name": "SEO Optimization", "min": 99, "max": 299, "recurring": True, "period": "monthly"},
    "performance_optimization": {"name": "Speed Optimization", "min": 149, "max": 399},
    "security_hardening": {"name": "Security Fix & SSL Setup", "min": 99, "max": 249},
    "accessibility_audit": {"name": "Accessibility Compliance Fix", "min": 199, "max": 499},
    "content_strategy": {"name": "Content Writing & Optimization", "min": 149, "max": 399, "recurring": True, "period": "monthly"},
    "local_seo": {"name": "Local SEO & Google Maps", "min": 79, "max": 199, "recurring": True, "period": "monthly"},
    "social_media": {"name": "Social Media Setup & Management", "min": 99, "max": 249, "recurring": True, "period": "monthly"},
    "email_marketing": {"name": "Email Marketing Setup", "min": 149, "max": 349},
    "analytics_setup": {"name": "Google Analytics & Tracking", "min": 79, "max": 199},
    "booking_system": {"name": "Online Booking System", "min": 249, "max": 699},
    "ecommerce": {"name": "Online Store Setup", "min": 499, "max": 1499},
}

_DELIVERABLES: dict[str, list[str]] = {
    "website_redesign": [
        "Custom responsive design mockups",
        "Mobile-first development",
        "Content migration and optimization",
        "Browser testing and QA",
        "30-day post-launch support",
    ],
    "seo_optimization": [
        "Keyword research and strategy",
        "On-page SEO optimization",
        "Technical SEO audit and fixes",
        "Local SEO setup and optimization",
        "Monthly ranking reports",
    ],
    "performance_optimization": [
        "Page speed audit and analysis",
        "Image and asset optimization",
        "Caching and CDN configuration",
        "Code minification and optimization",
        "Core Web Vitals improvement",
    ],
    "security_hardening": [
        "SSL certificate installation",
        "Security headers configuration",
        "Vulnerability patching",
        "Malware scanning setup",
        "Security monitoring configuration",
    ],
    "accessibility_audit": [
        "WCAG 2.1 compliance audit",
        "Screen reader compatibility fixes",
        "Keyboard navigation implementation",
        "Color contrast and readability fixes",
        "Accessibility statement creation",
    ],
    "content_strategy": [
        "Content audit and gap analysis",
        "Editorial calendar creation",
        "4 blog posts per month",
        "Service page optimization",
        "Call-to-action optimization",
    ],
    "local_seo": [
        "Google Business Profile optimization",
        "Local citation building",
        "Review management strategy",
        "Local keyword optimization",
        "Monthly local ranking reports",
    ],
    "social_media": [
        "Social media strategy development",
        "Profile setup and optimization",
        "Content calendar and scheduling",
        "Community engagement",
        "Monthly analytics reports",
    ],
    "email_marketing": [
        "Email platform setup",
        "Template design and creation",
        "Automation workflow setup",
        "List segmentation strategy",
        "A/B testing framework",
    ],
    "analytics_setup": [
        "Google Analytics 4 configuration",
        "Conversion tracking setup",
        "Custom dashboard creation",
        "Goal and event tracking",
        "Monthly reporting setup",
    ],
    "booking_system": [
        "Booking system selection and setup",
        "Calendar integration",
        "Automated confirmation emails",
        "Reminder system configuration",
        "Staff management portal",
    ],
    "ecommerce": [
        "E-commerce platform setup",
        "Product catalog creation",
        "Payment gateway integration",
        "Shipping and tax configuration",
        "Order management system",
    ],
}

_TIMELINES: dict[str, int] = {
    "website_redesign": 6,
    "seo_optimization": 4,
    "performance_optimization": 2,
    "security_hardening": 1,
    "accessibility_audit": 3,
    "content_strategy": 4,
    "local_seo": 2,
    "social_media": 2,
    "email_marketing": 3,
    "analytics_setup": 1,
    "booking_system": 3,
    "ecommerce": 8,
}

_PROBLEM_TO_SERVICE: dict[str, str] = {
    "Poor Search Visibility": "seo_optimization",
    "Slow Website Performance": "performance_optimization",
    "Security Vulnerabilities": "security_hardening",
    "Accessibility Issues": "accessibility_audit",
    "Poor User Experience": "website_redesign",
    "Weak Content": "content_strategy",
    "Missing Calls-to-Action": "website_redesign",
    "Not Mobile-Friendly": "website_redesign",
}


@dataclass
class ProposalProblem:
    title: str
    description: str
    impact: str
    severity: str  # critical | high | medium | low


@dataclass
class ProposalSolution:
    title: str
    description: str
    deliverables: list[str]
    timeline_weeks: int
    price_min: float
    price_max: float
    recurring: bool = False
    period: str = ""


@dataclass
class GeneratedProposal:
    title: str
    executive_summary: str
    problems: list[ProposalProblem]
    solutions: list[ProposalSolution]
    timeline: dict[str, Any]
    pricing: dict[str, Any]
    expected_roi: str
    total_value_min: float
    total_value_max: float
    valid_until: datetime


class ProposalGenerator:
    def generate(
        self,
        business_data: dict[str, Any],
        audit_data: Optional[dict[str, Any]] = None,
        contact_data: Optional[dict[str, Any]] = None,
        custom_services: Optional[list[str]] = None,
    ) -> GeneratedProposal:
        business_name = business_data.get("name", "Your Business")
        industry = business_data.get("industry", "")
        city = business_data.get("city", "")

        problems = self._identify_problems(audit_data)
        solutions = self._recommend_solutions(problems, custom_services)
        timeline = self._build_timeline(solutions)
        pricing = self._calculate_pricing(solutions)
        roi = self._estimate_roi(audit_data, pricing)

        title = f"Digital Growth Proposal for {business_name}"
        summary = self._generate_summary(business_name, city, problems, solutions)

        total_min = sum(s.price_min for s in solutions)
        total_max = sum(s.price_max for s in solutions)

        return GeneratedProposal(
            title=title,
            executive_summary=summary,
            problems=problems,
            solutions=solutions,
            timeline=timeline,
            pricing=pricing,
            expected_roi=roi,
            total_value_min=total_min,
            total_value_max=total_max,
            valid_until=datetime.now(timezone.utc) + timedelta(days=30),
        )

    def generate_html(self, proposal: GeneratedProposal, business_data: dict[str, Any]) -> str:
        business_name = business_data.get("name", "")

        sev_colors = {"critical": "#dc2626", "high": "#ea580c", "medium": "#ca8a04", "low": "#16a34a"}

        problems_html = "".join(
            f"""<div style="margin-bottom:16px;padding:16px;border-left:4px solid {sev_colors.get(p.severity,'#6b7280')};background:#f9fafb;border-radius:4px;">
<h4 style="margin:0 0 8px 0;color:#111827;">{p.title}</h4>
<p style="margin:0 0 8px 0;color:#4b5563;">{p.description}</p>
<p style="margin:0;color:{sev_colors.get(p.severity,'#6b7280')};font-weight:600;">Impact: {p.impact}</p>
</div>"""
            for p in proposal.problems
        )

        solutions_html = "".join(
            f"""<div style="margin-bottom:20px;padding:20px;border:1px solid #e5e7eb;border-radius:8px;">
<h4 style="margin:0 0 8px 0;color:#111827;">{s.title}</h4>
<p style="margin:0 0 12px 0;color:#4b5563;">{s.description}</p>
<p style="margin:0 0 8px 0;font-weight:600;color:#059669;">${s.price_min:,.0f}–${s.price_max:,.0f}{' / ' + s.period if s.recurring else ''}</p>
<p style="margin:0 0 4px 0;font-weight:600;color:#374151;">Timeline: {s.timeline_weeks} weeks</p>
<ul style="margin:8px 0 0 0;padding-left:20px;color:#4b5563;">{"".join(f"<li>{d}</li>" for d in s.deliverables)}</ul>
</div>"""
            for s in proposal.solutions
        )

        phases_html = "".join(
            f"""<div style="margin-bottom:12px;padding:12px;background:#f0fdf4;border-radius:4px;">
<strong>{name}</strong>: {data.get('description','')} ({data.get('duration','')})
</div>"""
            for name, data in proposal.timeline.get("phases", {}).items()
        )

        return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>{proposal.title}</title></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;max-width:800px;margin:0 auto;padding:40px;color:#111827;line-height:1.6;">
<div style="text-align:center;margin-bottom:40px;padding:30px;background:linear-gradient(135deg,#1e40af,#7c3aed);border-radius:12px;color:white;">
  <h1 style="margin:0 0 10px 0;font-size:28px;">{proposal.title}</h1>
  <p style="margin:0;opacity:0.9;">Prepared for {business_name}</p>
  <p style="margin:8px 0 0 0;opacity:0.7;font-size:14px;">Valid until {proposal.valid_until.strftime('%B %d, %Y')}</p>
</div>
<div style="margin-bottom:40px;">
  <h2 style="color:#1e40af;border-bottom:2px solid #e5e7eb;padding-bottom:8px;">Executive Summary</h2>
  <p style="color:#374151;font-size:16px;">{proposal.executive_summary}</p>
</div>
<div style="margin-bottom:40px;">
  <h2 style="color:#1e40af;border-bottom:2px solid #e5e7eb;padding-bottom:8px;">Issues Identified</h2>
  {problems_html}
</div>
<div style="margin-bottom:40px;">
  <h2 style="color:#1e40af;border-bottom:2px solid #e5e7eb;padding-bottom:8px;">Recommended Solutions</h2>
  {solutions_html}
</div>
<div style="margin-bottom:40px;">
  <h2 style="color:#1e40af;border-bottom:2px solid #e5e7eb;padding-bottom:8px;">Project Timeline</h2>
  {phases_html}
</div>
<div style="margin-bottom:40px;padding:24px;background:#f0f9ff;border-radius:8px;border:1px solid #bae6fd;">
  <h2 style="color:#1e40af;margin-top:0;">Investment Summary</h2>
  <p style="font-size:24px;font-weight:bold;color:#059669;">${proposal.total_value_min:,.0f}–${proposal.total_value_max:,.0f}</p>
  <p style="color:#4b5563;">{proposal.expected_roi}</p>
</div>
<div style="text-align:center;padding:30px;background:#f9fafb;border-radius:8px;">
  <h3 style="color:#111827;">Ready to Get Started?</h3>
  <p style="color:#4b5563;">Let's schedule a call to discuss this proposal and answer any questions.</p>
</div>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _identify_problems(self, audit_data: Optional[dict[str, Any]]) -> list[ProposalProblem]:
        if not audit_data:
            return [ProposalProblem(
                title="Website Performance Unknown",
                description="Without a detailed audit there may be hidden issues affecting your online performance.",
                impact="Potential loss of customers who can't find or use your website effectively.",
                severity="medium",
            )]

        checks = [
            ("seo_score", 55, "Poor Search Visibility",
             "Your website is not showing up in local search results, so customers searching for your services can't find you.",
             "You're losing potential customers every day to competitors who rank higher on Google.", "high"),
            ("speed_score", 55, "Slow Website Performance",
             "Your website takes too long to load — visitors leave before they even see what you offer.",
             "53% of mobile visitors abandon a site that takes over 3 seconds to load.", "critical"),
            ("security_score", 55, "Security Vulnerabilities",
             "Your website is missing basic security protections that modern browsers now flag as warnings.",
             "Visitors see 'Not Secure' warnings which immediately destroys trust.", "critical"),
            ("accessibility_score", 55, "Accessibility Issues",
             "Your website is difficult to use for people with disabilities or on small screens.",
             "You're excluding a portion of your potential customers unnecessarily.", "high"),
            ("ui_score", 50, "Poor User Experience",
             "Your website design makes it hard for visitors to find information or take action.",
             "Poor UX directly reduces calls, bookings, and walk-in traffic.", "medium"),
            ("content_score", 50, "Weak Content",
             "Your website doesn't have enough content to engage visitors or convince them to contact you.",
             "Visitors leave without taking action because there's nothing compelling to read.", "medium"),
            ("conversion_score", 45, "Missing Calls-to-Action",
             "Your website has no clear buttons or forms prompting visitors to call, book, or contact you.",
             "You're getting traffic but not converting it into actual customers.", "high"),
            ("mobile_score", 50, "Not Mobile-Friendly",
             "Your website doesn't display properly on phones — most of your customers are searching on mobile.",
             "Google penalises non-mobile sites and ranks them lower in search results.", "critical"),
        ]

        problems: list[ProposalProblem] = []
        for field_name, threshold, title, desc, impact, severity in checks:
            if audit_data.get(field_name, 100) < threshold:
                problems.append(ProposalProblem(title=title, description=desc, impact=impact, severity=severity))

        if not problems:
            problems.append(ProposalProblem(
                title="Room for Optimisation",
                description="While your website performs adequately there are areas that could be improved to gain a competitive edge.",
                impact="Competitors with better-optimised sites may be capturing your potential customers.",
                severity="low",
            ))
        return problems

    def _recommend_solutions(
        self,
        problems: list[ProposalProblem],
        custom_services: Optional[list[str]] = None,
    ) -> list[ProposalSolution]:
        service_keys: set[str] = set()
        for p in problems:
            key = _PROBLEM_TO_SERVICE.get(p.title)
            if key:
                service_keys.add(key)
        if custom_services:
            service_keys.update(custom_services)
        if not service_keys:
            service_keys = {"website_redesign", "seo_optimization"}

        solutions: list[ProposalSolution] = []
        for key in service_keys:
            svc = SERVICE_PRICING.get(key)
            if svc:
                solutions.append(ProposalSolution(
                    title=svc["name"],
                    description=f"Professional {svc['name'].lower()} to address identified issues.",
                    deliverables=_DELIVERABLES.get(key, ["Custom implementation", "Testing and QA", "Documentation"]),
                    timeline_weeks=_TIMELINES.get(key, 4),
                    price_min=float(svc["min"]),
                    price_max=float(svc["max"]),
                    recurring=svc.get("recurring", False),
                    period=svc.get("period", ""),
                ))
        return solutions

    def _build_timeline(self, solutions: list[ProposalSolution]) -> dict[str, Any]:
        phases: dict[str, Any] = {}
        week = 1

        buckets = [
            ("Phase 1: Quick Wins", [s for s in solutions if s.timeline_weeks <= 2]),
            ("Phase 2: Core Improvements", [s for s in solutions if 2 < s.timeline_weeks <= 4]),
            ("Phase 3: Growth & Optimisation", [s for s in solutions if s.timeline_weeks > 4]),
        ]

        for phase_name, items in buckets:
            if not items:
                continue
            max_w = max(s.timeline_weeks for s in items)
            phases[phase_name] = {
                "description": ", ".join(s.title for s in items),
                "duration": f"Weeks {week}–{week + max_w - 1}",
                "start_week": week,
                "end_week": week + max_w - 1,
            }
            week += max_w

        return {"phases": phases, "total_weeks": week - 1, "estimated_completion": f"{week - 1} weeks"}

    def _calculate_pricing(self, solutions: list[ProposalSolution]) -> dict[str, Any]:
        one_time_min = sum(s.price_min for s in solutions if not s.recurring)
        one_time_max = sum(s.price_max for s in solutions if not s.recurring)
        rec_min = sum(s.price_min for s in solutions if s.recurring)
        rec_max = sum(s.price_max for s in solutions if s.recurring)

        return {
            "one_time": {"min": one_time_min, "max": one_time_max},
            "recurring_monthly": {"min": rec_min, "max": rec_max},
            "total_first_year_min": one_time_min + rec_min * 12,
            "total_first_year_max": one_time_max + rec_max * 12,
            "services": [
                {
                    "name": s.title,
                    "price_min": s.price_min,
                    "price_max": s.price_max,
                    "recurring": s.recurring,
                    "period": s.period,
                }
                for s in solutions
            ],
        }

    def _estimate_roi(self, audit_data: Optional[dict[str, Any]], pricing: dict[str, Any]) -> str:
        one_time_min = pricing["one_time"]["min"]
        one_time_max = pricing["one_time"]["max"]
        rec_min = pricing["recurring_monthly"]["min"]
        rec_max = pricing["recurring_monthly"]["max"]
        current = audit_data.get("overall_score", 0) if audit_data else 0

        parts = []
        if one_time_min > 0:
            parts.append(f"one-time setup from ${one_time_min:,.0f}–${one_time_max:,.0f}")
        if rec_min > 0:
            parts.append(f"ongoing support from ${rec_min:,.0f}/month")

        investment_str = " + ".join(parts) if parts else "a small one-time investment"

        if current < 40:
            outcome = "30–50% more website visitors and 2–3× more customer enquiries"
        elif current < 65:
            outcome = "20–35% improvement in local search rankings and more calls/walk-ins"
        else:
            outcome = "a competitive edge that keeps customers choosing you over competitors"

        return (
            f"For {investment_str}, most local businesses in your category see {outcome} "
            f"within 60–90 days. These improvements typically pay for themselves within "
            f"the first 1–2 new customers you win from better online visibility."
        )

    def _generate_summary(
        self,
        business_name: str,
        city: str,
        problems: list[ProposalProblem],
        solutions: list[ProposalSolution],
    ) -> str:
        critical = sum(1 for p in problems if p.severity in ("critical", "high"))
        loc = f" in {city}" if city else ""
        return (
            f"After a comprehensive analysis of {business_name}'s{loc} digital presence, "
            f"we identified {len(problems)} area{'s' if len(problems) != 1 else ''} requiring attention"
            f"{f', including {critical} critical issue' + ('s' if critical != 1 else '') if critical else ''}. "
            f"This proposal outlines {len(solutions)} targeted solution{'s' if len(solutions) != 1 else ''} "
            f"designed to strengthen your online presence, attract more customers, and grow your business. "
            f"Each recommendation is backed by data from our audit and tailored to your specific industry and market."
        )

    def generate_ai_proposal(
        self,
        business_data: dict,
        audit_data: dict | None = None,
        sender_name: str = "Web Services Team",
    ) -> "GeneratedProposal":
        """Generate AI-powered proposal using Gemini, fallback to rule-based."""
        import os
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return self.generate(business_data, audit_data, sender_name)
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            biz_name = business_data.get("name", "the business")
            industry = business_data.get("industry") or business_data.get("category", "local business")
            city = business_data.get("city", "")
            website = business_data.get("website_url", "no website")
            scores = ""
            if audit_data:
                scores = f"""
- SEO Score: {audit_data.get('seo_score', 'N/A')}/100
- Mobile Score: {audit_data.get('mobile_score', 'N/A')}/100
- Performance Score: {audit_data.get('speed_score', 'N/A')}/100
- Security Score: {audit_data.get('security_score', 'N/A')}/100
- UI Score: {audit_data.get('ui_score', 'N/A')}/100
- Overall Score: {audit_data.get('overall_score', 'N/A')}/100"""
            prompt = f"""You are a professional web agency writing a proposal for a potential client.

Business: {biz_name}
Industry: {industry}
City: {city}
Website: {website}
{scores}

Write a compelling, personalized web services proposal. Include:
1. Executive Summary (2-3 sentences specific to their business)
2. Key Problems Found (3-5 specific issues based on the audit scores)
3. Recommended Services (3-5 services with brief descriptions)
4. Expected Business Impact (specific to their industry)
5. Investment Estimate (use ranges: Basic $500-1500, Standard $1500-3500, Premium $3500-7000)
6. Why Act Now (urgency based on their situation)

Keep it under 400 words. Be specific to {industry} businesses in {city}. Sound human, not corporate."""
            response = model.generate_content(prompt)
            ai_text = response.text.strip()
            # Build a GeneratedProposal from AI text
            base = self.generate(business_data, audit_data, sender_name)
            base.executive_summary = ai_text
            return base
        except Exception:
            return self.generate(business_data, audit_data, sender_name)
