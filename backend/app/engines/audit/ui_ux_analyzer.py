"""
UIUXAnalyzer — heuristic UI/UX analysis based on HTML structure and,
optionally, a captured screenshot (Pillow colour-palette extraction).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class UIUXIssue:
    type: str
    severity: str       # critical | high | medium | low | info
    message: str
    recommendation: str = ""
    category: str = "ui_ux"

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class UIUXReport:
    score: float
    issues: List[UIUXIssue] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "issues": [i.to_dict() for i in self.issues],
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# CSS framework signatures
# ---------------------------------------------------------------------------

_CSS_FRAMEWORKS: Dict[str, List[re.Pattern]] = {
    "Bootstrap": [
        re.compile(r"bootstrap", re.I),
        re.compile(r'class="[^"]*\bcol-(?:xs|sm|md|lg|xl)-\d', re.I),
        re.compile(r'class="[^"]*\b(?:btn-primary|navbar-brand|container-fluid)\b', re.I),
    ],
    "Tailwind CSS": [
        re.compile(r"tailwind", re.I),
        re.compile(r'class="[^"]*\b(?:flex|grid|text-(?:sm|lg|xl)|bg-(?:blue|red|green|gray)-\d{3})\b', re.I),
        re.compile(r'class="[^"]*\bpx-\d|py-\d|mx-\d|my-\d\b', re.I),
    ],
    "Bulma": [
        re.compile(r"bulma", re.I),
        re.compile(r'class="[^"]*\b(?:is-primary|columns|column|hero-body)\b', re.I),
    ],
    "Foundation": [
        re.compile(r"foundation", re.I),
        re.compile(r'class="[^"]*\b(?:callout|reveal|orbit)\b', re.I),
    ],
    "Materialize": [
        re.compile(r"materialize", re.I),
        re.compile(r'class="[^"]*\b(?:waves-effect|card-panel|col s\d)\b', re.I),
    ],
    "Material UI": [
        re.compile(r"@mui|material-ui|MuiButton", re.I),
    ],
    "Chakra UI": [
        re.compile(r"chakra-ui|@chakra", re.I),
    ],
}

_JS_FRAMEWORKS: Dict[str, List[re.Pattern]] = {
    "React": [
        re.compile(r"react(?:\.min)?\.js|react-dom", re.I),
        re.compile(r"__reactFiber|__reactInternalInstance", re.I),
        re.compile(r"data-reactroot|data-reactid", re.I),
    ],
    "Vue.js": [
        re.compile(r"vue(?:\.min)?\.js", re.I),
        re.compile(r"v-bind:|v-on:|v-model|v-if|v-for", re.I),
        re.compile(r"__vue__", re.I),
    ],
    "Angular": [
        re.compile(r"angular(?:\.min)?\.js|@angular", re.I),
        re.compile(r"ng-app|ng-controller|ng-model|ngIf", re.I),
    ],
    "jQuery": [
        re.compile(r"jquery(?:\.min)?\.js", re.I),
        re.compile(r"\$\(document\)\.ready|jQuery\.", re.I),
    ],
    "Next.js": [
        re.compile(r"/_next/static|__NEXT_DATA__", re.I),
    ],
    "Nuxt.js": [
        re.compile(r"/__nuxt/|__NUXT__", re.I),
    ],
    "WordPress": [
        re.compile(r"/wp-content/|/wp-includes/|wp-json", re.I),
    ],
    "Shopify": [
        re.compile(r"cdn\.shopify\.com|Shopify\.theme", re.I),
    ],
    "Wix": [
        re.compile(r"static\.parastorage\.com|wix\.com", re.I),
    ],
    "Squarespace": [
        re.compile(r"squarespace\.com", re.I),
    ],
    "Webflow": [
        re.compile(r"webflow\.com", re.I),
    ],
}

# ---------------------------------------------------------------------------
# CTA detection patterns
# ---------------------------------------------------------------------------

_CTA_TEXT_PATTERNS = re.compile(
    r"\b(get started|sign up|try free|buy now|order now|contact us|request|"
    r"schedule|book|demo|learn more|subscribe|download|start|join|free trial|"
    r"call us|get quote|claim|shop now)\b",
    re.I,
)

_TRUST_SIGNAL_PATTERNS = re.compile(
    r"(ssl|secure|verified|trusted|certified|guarantee|money.back|no.risk|"
    r"testimonial|review|rated|stars|award|featured in|as seen|partner|"
    r"accredited|licensed|insured)",
    re.I,
)

_SOCIAL_PROOF_PATTERNS = re.compile(
    r"(customers|clients|users|members|reviews|ratings|testimonial|"
    r"case stud|portfolio|success stor)",
    re.I,
)

_CONTACT_PATTERNS = re.compile(
    r"(\+?[\d\s\-\(\)]{7,}|[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.I,
)


# ---------------------------------------------------------------------------
# Analyser
# ---------------------------------------------------------------------------


class UIUXAnalyzer:
    """
    Heuristic-based UI/UX analysis.

    Parameters
    ----------
    screenshot_path:
        Optional path to a PNG screenshot.  When supplied, Pillow is used to
        extract the dominant colour palette.
    """

    def __init__(self, screenshot_path: Optional[str] = None) -> None:
        self._screenshot_path = screenshot_path

    async def analyze(self, html: str, url: str) -> UIUXReport:
        soup = BeautifulSoup(html, "lxml")
        issues: List[UIUXIssue] = []
        metadata: Dict[str, Any] = {"url": url}

        # ---- Mobile viewport meta -----------------------------------
        _check_viewport_meta(soup, issues, metadata)

        # ---- CSS framework detection --------------------------------
        _detect_css_frameworks(html, soup, metadata)

        # ---- JS framework / CMS detection ---------------------------
        _detect_js_frameworks(html, soup, metadata)

        # ---- Responsive design indicators ---------------------------
        _check_responsive(soup, issues, metadata)

        # ---- Font stack analysis ------------------------------------
        _analyze_fonts(html, soup, metadata)

        # ---- Navigation structure -----------------------------------
        _analyze_navigation(soup, issues, metadata)

        # ---- CTA detection ------------------------------------------
        _check_ctas(soup, issues, metadata)

        # ---- Form quality -------------------------------------------
        _check_forms(soup, issues, metadata)

        # ---- Trust signals ------------------------------------------
        _check_trust_signals(soup, issues, metadata)

        # ---- Social proof -------------------------------------------
        _check_social_proof(soup, issues, metadata)

        # ---- Contact info visibility --------------------------------
        _check_contact_info(html, soup, issues, metadata)

        # ---- Broken / placeholder images ----------------------------
        _check_placeholder_images(soup, issues, metadata)

        # ---- Colour palette from screenshot (optional) --------------
        if self._screenshot_path:
            palette = _extract_colour_palette(self._screenshot_path)
            if palette:
                metadata["colour_palette"] = palette

        score = _calculate_score(issues)
        recommendations = _build_recommendations(issues)

        return UIUXReport(
            score=score,
            issues=issues,
            recommendations=recommendations,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_viewport_meta(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    metadata["has_viewport_meta"] = vp is not None
    if not vp:
        issues.append(
            UIUXIssue(
                "missing_viewport",
                "critical",
                "No viewport meta tag found.",
                "Add <meta name='viewport' content='width=device-width, initial-scale=1'> "
                "to ensure proper mobile rendering.",
            )
        )


def _detect_css_frameworks(
    html: str, soup: BeautifulSoup, metadata: Dict[str, Any]
) -> None:
    detected = []
    for name, patterns in _CSS_FRAMEWORKS.items():
        for pat in patterns:
            if pat.search(html):
                detected.append(name)
                break
    metadata["css_frameworks"] = detected


def _detect_js_frameworks(
    html: str, soup: BeautifulSoup, metadata: Dict[str, Any]
) -> None:
    detected = []
    for name, patterns in _JS_FRAMEWORKS.items():
        for pat in patterns:
            if pat.search(html):
                detected.append(name)
                break
    metadata["js_frameworks"] = detected
    metadata["tech_stack"] = detected  # convenience alias


def _check_responsive(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    # Look for media query hints in <style> tags or linked sheets
    has_media_queries = False
    for style in soup.find_all("style"):
        if "@media" in (style.string or ""):
            has_media_queries = True
            break

    # Look for responsive CSS classes (Bootstrap / Tailwind)
    resp_class_pattern = re.compile(
        r"\b(col-(?:xs|sm|md|lg|xl)-\d|sm:|md:|lg:|xl:|responsive|d-none|d-flex)\b"
    )
    body_html = str(soup.body or soup)
    has_responsive_classes = bool(resp_class_pattern.search(body_html))

    metadata["has_media_queries"] = has_media_queries
    metadata["has_responsive_classes"] = has_responsive_classes
    metadata["likely_responsive"] = has_media_queries or has_responsive_classes

    if not has_media_queries and not has_responsive_classes:
        issues.append(
            UIUXIssue(
                "not_responsive",
                "critical",
                "No responsive design indicators detected (no media queries or responsive classes).",
                "Implement a mobile-first responsive layout using CSS media queries or a framework.",
            )
        )


def _analyze_fonts(
    html: str, soup: BeautifulSoup, metadata: Dict[str, Any]
) -> None:
    fonts_detected: List[str] = []
    # Google Fonts
    for link in soup.find_all("link", href=re.compile(r"fonts\.googleapis\.com", re.I)):
        href = link.get("href", "")
        families = re.findall(r"family=([^&|]+)", href)
        for fam in families:
            name = fam.split(":")[0].replace("+", " ")
            fonts_detected.append(name)

    # Adobe Fonts / Typekit
    if re.search(r"typekit|use\.typekit|use\.edgefonts", html, re.I):
        fonts_detected.append("Adobe Fonts")

    # System font stack in inline/embedded CSS
    sys_font_pat = re.compile(
        r"font-family\s*:\s*([^;\"'{}]+)", re.I
    )
    for style in soup.find_all("style"):
        for match in sys_font_pat.finditer(style.string or ""):
            font_list = match.group(1).strip()
            # Only add short, legible entries
            if len(font_list) < 80:
                fonts_detected.append(font_list)

    metadata["fonts"] = list(dict.fromkeys(fonts_detected))[:10]  # deduplicated


def _analyze_navigation(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    nav_elements = soup.find_all("nav")
    header_navs = soup.find_all(["header"])
    metadata["nav_count"] = len(nav_elements)

    if not nav_elements and not header_navs:
        issues.append(
            UIUXIssue(
                "missing_navigation",
                "high",
                "No <nav> or <header> element detected.",
                "Add a clear navigation structure to help users find content.",
            )
        )
        return

    # Check for excessively deep nav nesting (more than 2 levels)
    for nav in nav_elements:
        uls = nav.find_all("ul")
        depth = max((len(list(_ul_parents(ul, nav))) for ul in uls), default=0)
        if depth > 2:
            issues.append(
                UIUXIssue(
                    "deep_navigation",
                    "low",
                    f"Navigation has {depth} nesting levels — may be hard to navigate.",
                    "Keep navigation to 2 levels maximum for clarity.",
                )
            )
            break


def _ul_parents(el: Any, stop_at: Any) -> Any:
    parent = el.parent
    while parent and parent != stop_at:
        if parent.name == "ul":
            yield parent
        parent = parent.parent


def _check_ctas(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    cta_elements: List[str] = []

    # Primary: buttons and <a> tags with CTA-like text
    for el in soup.find_all(["a", "button"]):
        text = el.get_text(strip=True)
        if _CTA_TEXT_PATTERNS.search(text):
            cta_elements.append(text[:80])

    # Secondary: inputs of type submit
    for inp in soup.find_all("input", attrs={"type": re.compile("^submit$", re.I)}):
        val = inp.get("value", "").strip()
        if val:
            cta_elements.append(val[:80])

    metadata["cta_count"] = len(cta_elements)
    metadata["cta_texts"] = list(dict.fromkeys(cta_elements))[:10]

    if len(cta_elements) == 0:
        issues.append(
            UIUXIssue(
                "no_cta",
                "high",
                "No clear call-to-action (CTA) detected on the page.",
                "Add prominent CTAs (e.g. 'Get Started', 'Contact Us') to guide visitors.",
            )
        )
    elif len(cta_elements) > 10:
        issues.append(
            UIUXIssue(
                "too_many_ctas",
                "low",
                f"Page has {len(cta_elements)} CTA-like elements — may cause choice paralysis.",
                "Prioritise 1-3 primary CTAs per page to focus user attention.",
            )
        )


def _check_forms(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    forms = soup.find_all("form")
    metadata["form_count"] = len(forms)
    if not forms:
        return

    issues_found = 0
    for form in forms:
        # Check for submit button
        submit = form.find(
            ["button", "input"],
            attrs={"type": re.compile("^submit$", re.I)},
        ) or form.find("button", type=None)
        if not submit:
            issues_found += 1

        # Check for placeholder-only labels (anti-pattern)
        inputs_only_placeholder = [
            inp for inp in form.find_all("input")
            if inp.get("placeholder") and not inp.get("id")
            and not form.find("label", attrs={"for": inp.get("id", "__none__")})
        ]
        if inputs_only_placeholder:
            issues_found += 1

    if issues_found:
        issues.append(
            UIUXIssue(
                "form_quality",
                "medium",
                f"{issues_found} form issue(s): missing submit button or placeholder-only labelling.",
                "Ensure every form has a clear submit action and visible labels (not just placeholders).",
            )
        )


def _check_trust_signals(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    body_text = soup.get_text(" ", strip=True)
    has_trust = bool(_TRUST_SIGNAL_PATTERNS.search(body_text))

    # Look for SSL badge / security icons
    ssl_imgs = soup.find_all(
        "img",
        attrs={"alt": re.compile(r"ssl|secure|trusted|verified", re.I)},
    )
    has_ssl_badge = len(ssl_imgs) > 0

    metadata["has_trust_signals"] = has_trust or has_ssl_badge
    metadata["has_ssl_badge"] = has_ssl_badge

    if not has_trust and not has_ssl_badge:
        issues.append(
            UIUXIssue(
                "missing_trust_signals",
                "medium",
                "No trust signals detected (SSL badges, guarantees, certifications, or testimonials).",
                "Add social proof elements and trust badges to reduce conversion friction.",
            )
        )


def _check_social_proof(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    body_text = soup.get_text(" ", strip=True)
    has_social_proof = bool(_SOCIAL_PROOF_PATTERNS.search(body_text))

    # Detect star ratings
    star_elements = soup.find_all(
        attrs={"class": re.compile(r"star|rating|review", re.I)}
    )
    has_ratings = len(star_elements) > 0

    metadata["has_social_proof"] = has_social_proof or has_ratings
    metadata["has_star_ratings"] = has_ratings

    if not has_social_proof and not has_ratings:
        issues.append(
            UIUXIssue(
                "missing_social_proof",
                "low",
                "No social proof elements detected (testimonials, ratings, case studies).",
                "Add customer testimonials, star ratings, or case studies to build credibility.",
            )
        )


def _check_contact_info(
    html: str,
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    body_text = soup.get_text(" ", strip=True)

    # Phone number
    phone_pattern = re.compile(r"\+?[\d][\d\s\-\(\)\.]{6,}\d")
    phones = phone_pattern.findall(body_text)
    has_phone = len(phones) > 0

    # Email address
    email_pattern = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
    has_email = bool(email_pattern.search(body_text)) or bool(
        soup.find("a", href=re.compile(r"^mailto:", re.I))
    )

    # Address
    address_pattern = re.compile(
        r"\d{1,5}\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|"
        r"Boulevard|Blvd|Court|Ct|Place|Pl|Way)\b",
        re.I,
    )
    has_address = bool(address_pattern.search(body_text))

    metadata["has_phone"] = has_phone
    metadata["has_email"] = has_email
    metadata["has_address"] = has_address
    metadata["contact_score"] = sum([has_phone, has_email, has_address])

    if not has_phone and not has_email:
        issues.append(
            UIUXIssue(
                "missing_contact_info",
                "high",
                "No phone number or email address visible on the page.",
                "Display contact information prominently — at minimum a phone number or email.",
            )
        )
    elif not has_phone:
        issues.append(
            UIUXIssue(
                "missing_phone",
                "medium",
                "No phone number detected.",
                "Add a phone number to increase trust and enable direct contact.",
            )
        )


def _check_placeholder_images(
    soup: BeautifulSoup,
    issues: List[UIUXIssue],
    metadata: Dict[str, Any],
) -> None:
    placeholder_srcs = re.compile(
        r"(placeholder|via\.placeholder|placehold\.it|picsum|lorempixel|dummyimage)",
        re.I,
    )
    bad = [
        img for img in soup.find_all("img")
        if placeholder_srcs.search(img.get("src", ""))
    ]
    metadata["placeholder_images"] = len(bad)
    if bad:
        issues.append(
            UIUXIssue(
                "placeholder_images",
                "high",
                f"{len(bad)} placeholder image(s) still in use on the page.",
                "Replace all placeholder images with real, optimised business imagery.",
            )
        )


# ---------------------------------------------------------------------------
# Colour palette extraction via Pillow
# ---------------------------------------------------------------------------


def _extract_colour_palette(
    image_path: str, n_colors: int = 8
) -> Optional[List[str]]:
    """
    Return a list of dominant hex colour strings from the screenshot.
    Returns None if Pillow is unavailable or the file cannot be read.
    """
    try:
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        # Downsample to speed up quantize
        img.thumbnail((400, 400))
        quantized = img.quantize(colors=n_colors, method=Image.Quantize.MEDIANCUT)
        palette_data = quantized.getpalette()  # flat list: R,G,B,R,G,B,...
        if not palette_data:
            return None
        hex_colours: List[str] = []
        for i in range(0, n_colors * 3, 3):
            r, g, b = palette_data[i], palette_data[i + 1], palette_data[i + 2]
            hex_colours.append(f"#{r:02x}{g:02x}{b:02x}")
        return hex_colours
    except Exception as exc:
        logger.debug("Colour palette extraction failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS = {"critical": 20, "high": 10, "medium": 5, "low": 2, "info": 0}


def _calculate_score(issues: List[UIUXIssue]) -> float:
    penalty = sum(_SEVERITY_WEIGHTS.get(i.severity, 0) for i in issues)
    return max(0.0, min(100.0, 100.0 - penalty))


def _build_recommendations(issues: List[UIUXIssue]) -> List[Dict[str, Any]]:
    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    recs = []
    for issue in issues:
        if issue.recommendation:
            recs.append(
                {
                    "category": issue.category,
                    "priority": priority_map.get(issue.severity, 5),
                    "title": issue.type.replace("_", " ").title(),
                    "description": issue.recommendation,
                    "severity": issue.severity,
                }
            )
    recs.sort(key=lambda r: r["priority"])
    return recs
