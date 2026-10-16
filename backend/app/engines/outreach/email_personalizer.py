from __future__ import annotations

import logging
from dataclasses import dataclass
from string import Template
from typing import Any, Optional

logger = logging.getLogger(__name__)

INDUSTRY_TEMPLATES = {
    "restaurant": {
        "pain_points": [
            "Your website isn't showing up in local search results for '{city} restaurants'",
            "Potential customers can't find your menu online or it's not mobile-friendly",
            "You're missing out on online reservations and orders",
            "Your Google Business Profile may not be optimized for local discovery",
        ],
        "services": [
            "Local SEO optimization for restaurant searches",
            "Mobile-responsive menu design with online ordering",
            "Google Business Profile optimization",
            "Social media presence management",
        ],
        "improvements": ["30-50% increase in online visibility", "25% more table reservations", "Higher Google Maps ranking"],
    },
    "gym": {
        "pain_points": [
            "Your website doesn't effectively convert visitors into trial members",
            "Missing class schedules, pricing, and virtual tour content",
            "Poor mobile experience for members checking gym hours",
            "No automated lead nurturing for people who visit but don't sign up",
        ],
        "services": [
            "Conversion-optimized landing pages for membership sign-ups",
            "Class schedule and booking system integration",
            "Member portal development",
            "Automated email sequences for trial leads",
        ],
        "improvements": ["40% increase in trial sign-ups", "Better member retention", "Automated lead follow-up"],
    },
    "clinic": {
        "pain_points": [
            "Patients can't easily book appointments online",
            "Your website lacks essential trust signals for healthcare",
            "Missing patient testimonials and service descriptions",
            "Your site may not meet healthcare accessibility standards",
        ],
        "services": [
            "Online appointment booking integration",
            "HIPAA-compliant website design",
            "Patient review management system",
            "Healthcare SEO for local medical searches",
        ],
        "improvements": ["50% reduction in phone booking time", "More new patient inquiries", "Improved patient experience"],
    },
    "real_estate": {
        "pain_points": [
            "Property listings aren't optimized for search engines",
            "No IDX integration or it's slow and outdated",
            "Lead capture forms aren't converting visitors to inquiries",
            "Missing virtual tour and video walkthrough capabilities",
        ],
        "services": [
            "IDX-integrated property search with modern UX",
            "Virtual tour and video walkthrough setup",
            "Lead capture optimization and CRM integration",
            "Neighborhood and market report pages for SEO",
        ],
        "improvements": ["More qualified buyer leads", "Better listing visibility", "Automated lead nurturing"],
    },
    "hotel": {
        "pain_points": [
            "Your direct booking rate is low compared to OTA referrals",
            "Website doesn't showcase rooms and amenities effectively",
            "Missing rate comparison or best-price guarantee messaging",
            "Slow page load times drive potential guests to competitors",
        ],
        "services": [
            "Direct booking engine optimization",
            "Visual storytelling with room galleries and virtual tours",
            "Performance optimization for faster page loads",
            "Review aggregation and reputation management",
        ],
        "improvements": ["15-25% increase in direct bookings", "Reduced OTA commission costs", "Better guest conversion"],
    },
    "salon": {
        "pain_points": [
            "Clients can't book appointments online when you're busy with clients",
            "Your portfolio and before/after gallery isn't showcased well",
            "Missing service menu with clear pricing",
            "No automated reminders for repeat appointments",
        ],
        "services": [
            "Online booking system with service selection",
            "Portfolio gallery and before/after showcase",
            "Automated appointment reminders and follow-ups",
            "Social media integration for Instagram portfolio",
        ],
        "improvements": ["Reduce no-shows by 40%", "More bookings during off-peak hours", "Build repeat clientele"],
    },
    "law_firm": {
        "pain_points": [
            "Your website doesn't establish credibility and trust",
            "Potential clients can't find you for specific legal practice areas",
            "No secure client intake or consultation booking system",
            "Missing attorney profiles and case results",
        ],
        "services": [
            "Authority-building content strategy for practice areas",
            "Secure client intake and consultation scheduling",
            "Attorney profile pages with credentials and results",
            "Legal-specific SEO for practice area searches",
        ],
        "improvements": ["More qualified consultation requests", "Better conversion from search", "Enhanced professional credibility"],
    },
    "construction": {
        "pain_points": [
            "Your project portfolio doesn't show the quality of your work",
            "No clear way for potential clients to request estimates",
            "Missing service area information and specializations",
            "Your site doesn't rank for local contractor searches",
        ],
        "services": [
            "Project portfolio with photo galleries and case studies",
            "Online estimate request system",
            "Service area pages for local SEO",
            "Review and testimonial showcase",
        ],
        "improvements": ["More estimate requests", "Better project leads", "Establish expertise in your area"],
    },
    "security": {
        "pain_points": [
            "Your website doesn't convey professionalism and trust",
            "Potential clients can't easily request security assessments",
            "Missing certifications, credentials, and case studies",
            "No differentiation from competitors in search results",
        ],
        "services": [
            "Professional website redesign with trust signals",
            "Online security assessment request forms",
            "Certification and credential showcase",
            "Industry-specific content marketing",
        ],
        "improvements": ["More security contract inquiries", "Higher close rate with credibility", "Better search visibility"],
    },
    "default": {
        "pain_points": [
            "Your website may be losing potential customers due to usability issues",
            "You're not ranking well for local searches in your industry",
            "Your site doesn't effectively convert visitors into leads",
            "Missing mobile optimization is costing you customers",
        ],
        "services": [
            "Website redesign and optimization",
            "Search engine optimization (SEO)",
            "Conversion rate optimization",
            "Mobile-responsive design",
        ],
        "improvements": ["Improved online visibility", "More qualified leads", "Better customer conversion"],
    },
}


@dataclass
class PersonalizedEmail:
    subject: str
    body_html: str
    body_text: str
    variables_used: dict[str, str]


class EmailPersonalizer:
    def personalize(
        self,
        template_subject: str,
        template_body: str,
        business_data: dict[str, Any],
        audit_data: Optional[dict[str, Any]] = None,
        contact_data: Optional[dict[str, Any]] = None,
    ) -> PersonalizedEmail:
        industry = self._normalize_industry(business_data.get("industry", ""))
        industry_config = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["default"])

        variables = self._build_variables(business_data, audit_data, contact_data, industry_config)
        subject = self._render_template(template_subject, variables)
        body_html = self._render_template(template_body, variables)
        body_text = self._html_to_text(body_html)

        return PersonalizedEmail(
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            variables_used=variables,
        )

    def generate_outreach_email(
        self,
        business_data: dict[str, Any],
        audit_data: Optional[dict[str, Any]] = None,
        contact_data: Optional[dict[str, Any]] = None,
        sender_name: str = "Web Services Team",
    ) -> PersonalizedEmail:
        industry = self._normalize_industry(business_data.get("industry", ""))
        industry_config = INDUSTRY_TEMPLATES.get(industry, INDUSTRY_TEMPLATES["default"])

        contact_name = ""
        if contact_data:
            contact_name = contact_data.get("first_name") or contact_data.get("full_name", "")

        greeting = f"Hi {contact_name}," if contact_name else f"Hi {business_data.get('name', 'there')} team,"

        city = business_data.get("city", "your area")
        pain_points_html = ""
        if audit_data:
            pain_points_html = self._generate_audit_based_points(audit_data, industry_config)
        else:
            points = [p.replace("{city}", city) for p in industry_config["pain_points"][:3]]
            pain_points_html = "\n".join(f"<li>{p}</li>" for p in points)

        services_html = "\n".join(f"<li>{s}</li>" for s in industry_config["services"][:3])
        improvements_html = "\n".join(f"<li>{i}</li>" for i in industry_config["improvements"][:3])

        business_name = business_data.get("name", "your business")
        score = audit_data.get("overall_score", 0) if audit_data else 0
        score_text = f"Your website currently scores {score}/100 in our analysis." if score > 0 else ""

        industry_key = self._normalize_industry(industry)
        subject_variants = {
            "restaurant": [
                f"I noticed something about {business_name}'s online presence",
                f"A quick idea that could bring more customers to {business_name}",
                f"Your restaurant may be missing mobile customers",
                f"Found 3 opportunities on {business_name}'s website",
                f"Free website review for {business_name}",
            ],
            "gym": [
                f"Quick idea to get more members for {business_name}",
                f"Your gym website could convert more visitors",
                f"Found a few things holding {business_name} back online",
            ],
            "clinic": [
                f"Patients can't find {business_name} easily online",
                f"A quick look at {business_name}'s online booking experience",
                f"Small website fix that could bring more patients to {business_name}",
            ],
            "hotel": [
                f"More bookings for {business_name} — a quick idea",
                f"I reviewed {business_name}'s website and found something",
            ],
            "salon": [
                f"More clients for {business_name} — a simple website fix",
                f"Quick idea to fill your appointment calendar at {business_name}",
            ],
            "default": [
                f"Quick website review for {business_name}",
                f"Found an opportunity for {business_name} online",
                f"A small fix that could help {business_name} get more customers",
            ],
        }
        variants = subject_variants.get(industry_key, subject_variants["default"])
        import hashlib as _hs
        idx = int(_hs.md5(business_name.encode()).hexdigest(), 16) % len(variants)
        subject = variants[idx]

        body_html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; line-height: 1.6;">
<p>{greeting}</p>

<p>I recently came across {business_name} while researching businesses in {city} and took a quick look at your online presence. {score_text}</p>

<p><strong>Here's what I noticed:</strong></p>
<ul>
{pain_points_html}
</ul>

<p><strong>How we can help:</strong></p>
<ul>
{services_html}
</ul>

<p><strong>Expected improvements:</strong></p>
<ul>
{improvements_html}
</ul>

<p>I'd love to share a detailed analysis and discuss how we can help {business_name} attract more customers online. Would you be open to a quick 15-minute call this week?</p>

<p>Best regards,<br>{sender_name}</p>
</div>"""

        body_text = self._html_to_text(body_html)

        return PersonalizedEmail(
            subject=subject,
            body_html=body_html,
            body_text=body_text,
            variables_used={
                "business_name": business_name,
                "city": city,
                "industry": industry,
                "score": str(score),
            },
        )

    def generate_follow_up(
        self,
        business_data: dict[str, Any],
        follow_up_number: int = 1,
        contact_data: Optional[dict[str, Any]] = None,
        sender_name: str = "Web Services Team",
    ) -> PersonalizedEmail:
        business_name = business_data.get("name", "your business")
        contact_name = ""
        if contact_data:
            contact_name = contact_data.get("first_name") or contact_data.get("full_name", "")

        greeting = f"Hi {contact_name}," if contact_name else f"Hi {business_name} team,"

        if follow_up_number == 1:
            subject = f"Following up: website opportunity for {business_name}"
            body_html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; line-height: 1.6;">
<p>{greeting}</p>
<p>I reached out last week about some opportunities I noticed with your website. I understand you're busy, so I wanted to quickly follow up.</p>
<p>I put together a brief analysis showing specific areas where {business_name} could improve its online presence and attract more customers. I'd be happy to share it — no strings attached.</p>
<p>Would a quick call work for you this week? I'm flexible on timing.</p>
<p>Best regards,<br>{sender_name}</p>
</div>"""
        elif follow_up_number == 2:
            subject = f"Last thought: {business_name} online presence"
            body_html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; line-height: 1.6;">
<p>{greeting}</p>
<p>I know things get busy, so I'll keep this brief. I genuinely believe there are some quick wins that could help {business_name} get more customers from online search.</p>
<p>If now isn't the right time, no worries at all. But if you'd like to see the free analysis I've prepared, just reply with "interested" and I'll send it over.</p>
<p>Either way, wishing you all the best!</p>
<p>Best regards,<br>{sender_name}</p>
</div>"""
        else:
            subject = f"Resource for {business_name}"
            body_html = f"""<div style="font-family: Arial, sans-serif; max-width: 600px; line-height: 1.6;">
<p>{greeting}</p>
<p>I've compiled a free checklist of the top things businesses in your industry can do to improve their online presence. Would you like me to send it over?</p>
<p>No sales pitch — just genuinely useful tips you can implement yourself or with your current team.</p>
<p>Best regards,<br>{sender_name}</p>
</div>"""

        return PersonalizedEmail(
            subject=subject,
            body_html=body_html,
            body_text=self._html_to_text(body_html),
            variables_used={"business_name": business_name, "follow_up_number": str(follow_up_number)},
        )

    def generate_linkedin_message(
        self,
        business_data: dict[str, Any],
        contact_data: Optional[dict[str, Any]] = None,
    ) -> str:
        business_name = business_data.get("name", "your company")
        contact_name = ""
        if contact_data:
            contact_name = contact_data.get("first_name", "")

        greeting = f"Hi {contact_name}" if contact_name else "Hi"
        city = business_data.get("city", "your area")

        return f"""{greeting},

I came across {business_name} while researching businesses in {city}. I noticed some quick wins that could help improve your online visibility and bring in more customers.

Would you be open to a brief chat about it? I'd love to share what I found — completely free analysis, no strings attached.

Looking forward to connecting!"""

    def _normalize_industry(self, industry: str) -> str:
        if not industry:
            return "default"
        lower = industry.lower()
        mappings = {
            "restaurant": ["restaurant", "food", "dining", "cafe", "catering", "bakery", "pizzeria"],
            "gym": ["gym", "fitness", "yoga", "pilates", "crossfit", "health club", "sports"],
            "clinic": ["clinic", "medical", "dental", "healthcare", "doctor", "physician", "therapy", "chiropractic"],
            "real_estate": ["real estate", "property", "realty", "realtor", "housing", "apartment"],
            "hotel": ["hotel", "hospitality", "motel", "resort", "lodging", "inn", "airbnb"],
            "salon": ["salon", "beauty", "spa", "barber", "hair", "nail", "cosmetic", "aesthet"],
            "law_firm": ["law", "legal", "attorney", "lawyer", "solicitor", "counsel"],
            "construction": ["construction", "contractor", "building", "renovation", "plumbing", "electric", "roofing", "hvac"],
            "security": ["security", "guard", "surveillance", "alarm", "protection", "patrol"],
        }
        for key, keywords in mappings.items():
            if any(kw in lower for kw in keywords):
                return key
        return "default"

    def _build_variables(
        self,
        business_data: dict[str, Any],
        audit_data: Optional[dict[str, Any]],
        contact_data: Optional[dict[str, Any]],
        industry_config: dict,
    ) -> dict[str, str]:
        variables: dict[str, str] = {
            "business_name": business_data.get("name", ""),
            "city": business_data.get("city", ""),
            "state": business_data.get("state", ""),
            "industry": business_data.get("industry", ""),
            "website_url": business_data.get("website_url", ""),
        }
        if contact_data:
            variables["contact_name"] = contact_data.get("full_name", "")
            variables["contact_first_name"] = contact_data.get("first_name", "")
            variables["contact_email"] = contact_data.get("email", "")
        if audit_data:
            variables["overall_score"] = str(audit_data.get("overall_score", 0))
            variables["seo_score"] = str(audit_data.get("seo_score", 0))
            variables["performance_score"] = str(audit_data.get("performance_score", 0))
            variables["top_recommendation"] = audit_data.get("top_recommendation", "")
        return variables

    def _render_template(self, template_str: str, variables: dict[str, str]) -> str:
        try:
            tmpl = Template(template_str)
            return tmpl.safe_substitute(variables)
        except Exception:
            return template_str

    def _generate_audit_based_points(self, audit_data: dict[str, Any], industry_config: dict) -> str:
        points = []
        seo_score = audit_data.get("seo_score", 100)
        speed_score = audit_data.get("speed_score", audit_data.get("performance_score", 100))
        security_score = audit_data.get("security_score", 100)
        mobile_score = audit_data.get("mobile_score", 100)
        accessibility_score = audit_data.get("accessibility_score", 100)
        conversion_score = audit_data.get("conversion_score", 100)

        if seo_score < 50:
            points.append(f"Your website scores only {int(seo_score)}/100 for SEO — you're likely invisible in local search results")
        if speed_score < 50:
            points.append(f"Site speed score is {int(speed_score)}/100 — slow load times cause visitors to leave before seeing your content")
        if security_score < 55:
            points.append(f"Security score is {int(security_score)}/100 — visitors may see 'Not Secure' warnings that damage trust")
        if mobile_score < 55:
            points.append(f"Mobile score is {int(mobile_score)}/100 — your site doesn't display well on phones where most customers search")
        if accessibility_score < 55:
            points.append("Accessibility issues may be preventing some customers from using your site")
        if conversion_score < 50:
            points.append("No clear calls-to-action detected — visitors don't know how to contact or book with you")

        if not points:
            points = industry_config["pain_points"][:3]

        return "\n".join(f"<li>{p}</li>" for p in points[:4])

    def _html_to_text(self, html: str) -> str:
        import re
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"<li>", "• ", text)
        text = re.sub(r"</li>", "\n", text)
        text = re.sub(r"<p>", "\n", text)
        text = re.sub(r"</p>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
