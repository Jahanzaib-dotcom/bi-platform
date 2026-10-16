"""
AccessibilityAnalyzer — WCAG 2.1 AA-oriented accessibility checks via HTML
parsing (BeautifulSoup).  No browser execution is required; this runs purely
on the raw HTML string.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AccessibilityViolation:
    rule: str               # e.g. "img-alt", "label-for", "color-contrast"
    impact: str             # critical | serious | moderate | minor
    description: str
    wcag_criterion: str     # e.g. "1.1.1", "1.3.1"
    nodes: List[str] = field(default_factory=list)  # HTML snippets (up to 5)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class AccessibilityReport:
    score: float
    violations: List[AccessibilityViolation] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "violations": [v.to_dict() for v in self.violations],
            "recommendations": self.recommendations,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Analyser
# ---------------------------------------------------------------------------


class AccessibilityAnalyzer:
    """
    Perform static accessibility analysis on raw HTML.

    Coverage (WCAG 2.1 AA)
    ----------------------
    - 1.1.1  Non-text Content — images missing alt
    - 1.3.1  Info and Relationships — form inputs without labels
    - 1.3.5  Identify Input Purpose — autocomplete attributes
    - 1.4.3  Contrast (Minimum) — heuristic for pure black/white text blocks
    - 2.1.1  Keyboard — tabindex=-1 on interactive elements (flag only)
    - 2.4.1  Bypass Blocks — skip-navigation link
    - 2.4.2  Page Titled — document title exists
    - 2.4.6  Headings and Labels — heading hierarchy
    - 3.1.1  Language of Page — lang attribute on <html>
    - 4.1.2  Name, Role, Value — interactive elements with ARIA roles
    """

    async def analyze(self, url: str, html: str) -> AccessibilityReport:  # noqa: ARG002
        soup = BeautifulSoup(html, "lxml")
        violations: List[AccessibilityViolation] = []
        metadata: Dict[str, Any] = {}

        # 1.1.1 — Images without alt
        _check_img_alt(soup, violations, metadata)

        # 1.3.1 — Form inputs without associated labels
        _check_form_labels(soup, violations, metadata)

        # 1.3.5 — Autocomplete on common fields
        _check_autocomplete(soup, violations, metadata)

        # 2.4.1 — Skip navigation link
        _check_skip_link(soup, violations, metadata)

        # 2.4.2 — Page title
        _check_page_title(soup, violations, metadata)

        # 2.4.6 — Heading hierarchy
        _check_heading_hierarchy(soup, violations, metadata)

        # 3.1.1 — Language attribute
        _check_lang_attribute(soup, violations, metadata)

        # 4.1.2 — Interactive elements with ARIA
        _check_aria_roles(soup, violations, metadata)

        # 4.1.2 — Buttons and links without accessible names
        _check_interactive_names(soup, violations, metadata)

        # 2.1.1 — Keyboard — negative tabindex on focusable elements
        _check_keyboard_trap(soup, violations, metadata)

        # 1.4.4 — Text resize / zoom — meta viewport user-scalable=no
        _check_viewport_scalable(soup, violations, metadata)

        # Heuristic: colour contrast indicators (pure CSS not run in engine)
        _check_contrast_indicators(soup, violations, metadata)

        score = _calculate_score(violations)
        recommendations = _build_recommendations(violations)

        return AccessibilityReport(
            score=score,
            violations=violations,
            recommendations=recommendations,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_img_alt(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    imgs = soup.find_all("img")
    bad: List[str] = []
    for img in imgs:
        alt = img.get("alt")
        src = img.get("src", "")
        role = img.get("role", "")
        # Presentational images are exempt when role="presentation" or alt=""
        if role in ("presentation", "none"):
            continue
        if alt is None:
            bad.append(_node_snippet(img))
    metadata["images_total"] = len(imgs)
    metadata["images_missing_alt"] = len(bad)
    if bad:
        violations.append(
            AccessibilityViolation(
                rule="image-alt",
                impact="critical",
                description=f"{len(bad)} image(s) missing alt attribute.",
                wcag_criterion="1.1.1",
                nodes=bad[:5],
                recommendation=(
                    "Add descriptive alt text to every content image. "
                    "Use alt='' for decorative images."
                ),
            )
        )


def _check_form_labels(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    inputs = soup.find_all(
        "input",
        attrs={"type": lambda t: t not in ("hidden", "submit", "button", "reset", "image")
               if t else True},
    )
    inputs += soup.find_all("select")
    inputs += soup.find_all("textarea")

    # Build id -> label map
    label_for_ids = {
        label.get("for", "").strip()
        for label in soup.find_all("label")
        if label.get("for", "").strip()
    }

    bad: List[str] = []
    for el in inputs:
        el_id = el.get("id", "").strip()
        aria_label = el.get("aria-label", "").strip()
        aria_labelledby = el.get("aria-labelledby", "").strip()
        title = el.get("title", "").strip()
        # Acceptable if: label[for] matches id, or aria-label, or aria-labelledby, or title
        if aria_label or aria_labelledby or title:
            continue
        if el_id and el_id in label_for_ids:
            continue
        # Also acceptable if input is inside a <label>
        if el.find_parent("label"):
            continue
        bad.append(_node_snippet(el))

    metadata["unlabelled_inputs"] = len(bad)
    if bad:
        violations.append(
            AccessibilityViolation(
                rule="label",
                impact="critical",
                description=f"{len(bad)} form field(s) have no accessible label.",
                wcag_criterion="1.3.1",
                nodes=bad[:5],
                recommendation=(
                    "Associate every form field with a <label> element "
                    "(via for/id) or add an aria-label attribute."
                ),
            )
        )


def _check_autocomplete(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    _AUTOCOMPLETE_FIELDS = {
        "name": "name",
        "email": "email",
        "tel": "tel",
        "phone": "tel",
        "address": "street-address",
        "city": "address-level2",
        "zip": "postal-code",
        "postcode": "postal-code",
        "country": "country",
    }
    bad: List[str] = []
    for inp in soup.find_all("input"):
        name = (inp.get("name") or inp.get("id") or "").lower()
        type_ = (inp.get("type") or "text").lower()
        if type_ in ("hidden", "submit", "button", "reset", "checkbox", "radio"):
            continue
        for keyword, ac_val in _AUTOCOMPLETE_FIELDS.items():
            if keyword in name and not inp.get("autocomplete"):
                bad.append(_node_snippet(inp))
                break
    metadata["inputs_missing_autocomplete"] = len(bad)
    if bad:
        violations.append(
            AccessibilityViolation(
                rule="autocomplete",
                impact="moderate",
                description=f"{len(bad)} input(s) missing autocomplete attribute on common fields.",
                wcag_criterion="1.3.5",
                nodes=bad[:5],
                recommendation="Add autocomplete attributes to inputs that collect personal data.",
            )
        )


def _check_skip_link(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    # A skip link is typically the first anchor on the page that points to #main or #content
    first_links = soup.find_all("a", href=True, limit=5)
    has_skip = any(
        re.match(r"^#(main|content|maincontent|skip|primary)", a["href"].strip(), re.I)
        for a in first_links
    )
    metadata["has_skip_link"] = has_skip
    if not has_skip:
        violations.append(
            AccessibilityViolation(
                rule="bypass",
                impact="moderate",
                description="No skip navigation link found.",
                wcag_criterion="2.4.1",
                recommendation=(
                    "Add a 'Skip to main content' link as the first focusable "
                    "element: <a href='#main'>Skip to main content</a>."
                ),
            )
        )


def _check_page_title(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    title = soup.find("title")
    has_title = bool(title and title.get_text(strip=True))
    metadata["has_title"] = has_title
    if not has_title:
        violations.append(
            AccessibilityViolation(
                rule="document-title",
                impact="serious",
                description="Page has no <title> element.",
                wcag_criterion="2.4.2",
                recommendation="Add a descriptive <title> element to every page.",
            )
        )


def _check_heading_hierarchy(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    headings = soup.find_all(re.compile(r"^h[1-6]$"))
    levels = [int(h.name[1]) for h in headings]
    metadata["heading_count"] = len(levels)

    if not levels:
        violations.append(
            AccessibilityViolation(
                rule="heading-order",
                impact="moderate",
                description="No heading elements found on the page.",
                wcag_criterion="2.4.6",
                recommendation="Use heading elements (H1–H6) to structure page content.",
            )
        )
        return

    skips: List[str] = []
    prev = levels[0]
    for lvl in levels[1:]:
        if lvl > prev + 1:
            skips.append(f"H{prev} → H{lvl}")
        prev = lvl

    if skips:
        violations.append(
            AccessibilityViolation(
                rule="heading-order",
                impact="moderate",
                description=f"Heading hierarchy skips detected: {', '.join(skips)}.",
                wcag_criterion="2.4.6",
                recommendation="Use headings in sequential order without skipping levels.",
            )
        )


def _check_lang_attribute(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    html_tag = soup.find("html")
    lang = html_tag.get("lang", "").strip() if html_tag else ""
    metadata["html_lang"] = lang
    if not lang:
        violations.append(
            AccessibilityViolation(
                rule="html-has-lang",
                impact="serious",
                description="<html> element is missing the lang attribute.",
                wcag_criterion="3.1.1",
                recommendation="Add lang='en' (or the appropriate language code) to the <html> tag.",
            )
        )


def _check_aria_roles(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    _VALID_LANDMARK_ROLES = {
        "banner", "navigation", "main", "complementary",
        "contentinfo", "search", "form", "region",
    }
    # Landmark elements map
    landmark_elements = ["header", "nav", "main", "aside", "footer", "section"]
    roles_present = set()

    for el in soup.find_all(True):
        role = el.get("role", "")
        if role in _VALID_LANDMARK_ROLES:
            roles_present.add(role)
        if el.name in landmark_elements:
            roles_present.add(el.name)

    metadata["landmark_roles"] = list(roles_present)

    if "main" not in roles_present and not soup.find("main"):
        violations.append(
            AccessibilityViolation(
                rule="landmark-one-main",
                impact="moderate",
                description="Page has no <main> landmark or role='main'.",
                wcag_criterion="4.1.2",
                recommendation="Wrap primary content in a <main> element.",
            )
        )


def _check_interactive_names(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    bad_buttons: List[str] = []
    for btn in soup.find_all("button"):
        text = btn.get_text(strip=True)
        aria_label = btn.get("aria-label", "").strip()
        aria_labelledby = btn.get("aria-labelledby", "").strip()
        title = btn.get("title", "").strip()
        if not (text or aria_label or aria_labelledby or title):
            bad_buttons.append(_node_snippet(btn))

    bad_links: List[str] = []
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        aria_label = a.get("aria-label", "").strip()
        title = a.get("title", "").strip()
        has_img_with_alt = any(
            img.get("alt", "").strip()
            for img in a.find_all("img")
        )
        if not (text or aria_label or title or has_img_with_alt):
            bad_links.append(_node_snippet(a))

    metadata["buttons_without_name"] = len(bad_buttons)
    metadata["links_without_name"] = len(bad_links)

    if bad_buttons:
        violations.append(
            AccessibilityViolation(
                rule="button-name",
                impact="critical",
                description=f"{len(bad_buttons)} button(s) have no accessible name.",
                wcag_criterion="4.1.2",
                nodes=bad_buttons[:5],
                recommendation="Add descriptive text or aria-label to every button.",
            )
        )
    if bad_links:
        violations.append(
            AccessibilityViolation(
                rule="link-name",
                impact="serious",
                description=f"{len(bad_links)} link(s) have no accessible name.",
                wcag_criterion="4.1.2",
                nodes=bad_links[:5],
                recommendation=(
                    "Ensure every link has visible text, title, or aria-label "
                    "that describes its destination."
                ),
            )
        )


def _check_keyboard_trap(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    trapped: List[str] = []
    interactive = soup.find_all(["a", "button", "input", "select", "textarea"])
    for el in interactive:
        try:
            ti = int(el.get("tabindex", 0))
            if ti < 0:
                trapped.append(_node_snippet(el))
        except (ValueError, TypeError):
            pass
    metadata["keyboard_trapped_elements"] = len(trapped)
    if trapped:
        violations.append(
            AccessibilityViolation(
                rule="tabindex",
                impact="serious",
                description=f"{len(trapped)} interactive element(s) have tabindex < 0 and may be keyboard-inaccessible.",
                wcag_criterion="2.1.1",
                nodes=trapped[:5],
                recommendation=(
                    "Avoid tabindex values less than 0 on interactive elements "
                    "unless intentionally hiding them from focus."
                ),
            )
        )


def _check_viewport_scalable(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    viewport_meta = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
    if not viewport_meta:
        return
    content = viewport_meta.get("content", "").lower()
    user_scalable_no = "user-scalable=no" in content
    max_scale_1 = bool(
        re.search(r"maximum-scale\s*=\s*1(?:\.0+)?(?:\s|,|$)", content)
    )
    metadata["viewport_user_scalable"] = not user_scalable_no
    if user_scalable_no or max_scale_1:
        violations.append(
            AccessibilityViolation(
                rule="meta-viewport",
                impact="critical",
                description="Viewport meta tag disables user scaling (zoom).",
                wcag_criterion="1.4.4",
                recommendation=(
                    "Remove user-scalable=no and maximum-scale=1 from the viewport "
                    "meta tag to allow users to zoom the page."
                ),
            )
        )


def _check_contrast_indicators(
    soup: BeautifulSoup,
    violations: List[AccessibilityViolation],
    metadata: Dict[str, Any],
) -> None:
    """
    Heuristic only: detect inline styles with obviously low-contrast colour pairs
    (e.g. white-on-white, grey-on-grey).  Full contrast analysis requires
    rendering; this is a static signal.
    """
    low_contrast_patterns = [
        r"color\s*:\s*#(?:fff|ffffff|f9f9f9|fafafa|eeeeee|e0e0e0|ccc|cccccc)",
        r"color\s*:\s*rgba?\s*\(\s*2[0-4]\d\s*,\s*2[0-4]\d\s*,\s*2[0-4]\d",
        r"color\s*:\s*lightgr[ae]y",
        r"color\s*:\s*silver",
    ]
    combined = re.compile("|".join(low_contrast_patterns), re.I)
    suspects: List[str] = []
    for tag in soup.find_all(style=True):
        style = tag.get("style", "")
        if combined.search(style):
            suspects.append(_node_snippet(tag))
    metadata["potential_low_contrast_elements"] = len(suspects)
    if suspects:
        violations.append(
            AccessibilityViolation(
                rule="color-contrast",
                impact="serious",
                description=(
                    f"{len(suspects)} element(s) have inline styles that may produce "
                    "insufficient colour contrast (heuristic check)."
                ),
                wcag_criterion="1.4.3",
                nodes=suspects[:5],
                recommendation=(
                    "Ensure text has a minimum contrast ratio of 4.5:1 (AA) "
                    "against its background. Use a contrast checker tool."
                ),
            )
        )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_IMPACT_WEIGHTS = {
    "critical": 20,
    "serious": 12,
    "moderate": 6,
    "minor": 2,
}


def _calculate_score(violations: List[AccessibilityViolation]) -> float:
    penalty = sum(_IMPACT_WEIGHTS.get(v.impact, 0) for v in violations)
    return max(0.0, min(100.0, 100.0 - penalty))


def _build_recommendations(violations: List[AccessibilityViolation]) -> List[Dict[str, Any]]:
    priority_map = {"critical": 1, "serious": 2, "moderate": 3, "minor": 4}
    recs = []
    for v in violations:
        if v.recommendation:
            recs.append(
                {
                    "category": "accessibility",
                    "priority": priority_map.get(v.impact, 5),
                    "title": v.rule.replace("-", " ").title(),
                    "description": v.recommendation,
                    "wcag": v.wcag_criterion,
                    "impact": v.impact,
                }
            )
    recs.sort(key=lambda r: r["priority"])
    return recs


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _node_snippet(tag: Tag, max_len: int = 120) -> str:
    s = str(tag)
    # Keep only opening tag
    m = re.match(r"<[^>]+>", s)
    snippet = m.group(0) if m else s[:max_len]
    return snippet[:max_len]
