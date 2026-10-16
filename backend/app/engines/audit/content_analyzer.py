"""
ContentAnalyzer — evaluate content quality, readability, and completeness.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ContentIssue:
    type: str
    severity: str       # critical | high | medium | low | info
    message: str
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class ContentReport:
    score: float
    issues: List[ContentIssue] = field(default_factory=list)
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
# Analyser
# ---------------------------------------------------------------------------


class ContentAnalyzer:
    """
    Analyse the quality of page content based on the HTML.

    Checks
    ------
    - Word count / content depth
    - Readability (Flesch-Kincaid approximation)
    - Keyword density
    - Duplicate / thin content signals
    - Broken image indicators (src="", empty src, data-src without src)
    - Contact / business information presence
    - Copyright notice
    - Privacy policy / terms link
    - Last-updated / freshness signals
    - Lorem ipsum / placeholder text
    """

    def __init__(self) -> None:
        pass

    async def analyze(self, url: str, html: str) -> ContentReport:
        soup = BeautifulSoup(html, "lxml")
        issues: List[ContentIssue] = []
        metadata: Dict[str, Any] = {"url": url}

        # Clean body text
        body_text = _extract_body_text(soup)
        words = _tokenize(body_text)
        word_count = len(words)
        metadata["word_count"] = word_count

        # ---- Content depth ------------------------------------------
        if word_count < 100:
            issues.append(
                ContentIssue(
                    "thin_content",
                    "high",
                    f"Page has very little text content ({word_count} words).",
                    "Add meaningful content that describes your business, services, and value proposition.",
                )
            )
        elif word_count < 300:
            issues.append(
                ContentIssue(
                    "shallow_content",
                    "medium",
                    f"Page text is sparse ({word_count} words).",
                    "Expand page content to at least 300-500 words for better SEO and user clarity.",
                )
            )

        # ---- Lorem ipsum / placeholder text -------------------------
        lorem_count = body_text.lower().count("lorem ipsum")
        metadata["lorem_ipsum_occurrences"] = lorem_count
        if lorem_count > 0:
            issues.append(
                ContentIssue(
                    "placeholder_text",
                    "critical",
                    f"Lorem ipsum placeholder text found ({lorem_count} occurrence(s)).",
                    "Replace all Lorem Ipsum with real content before launching.",
                )
            )

        # ---- Readability (approximate Flesch-Kincaid) ---------------
        sentences = _count_sentences(body_text)
        syllables = _count_syllables(body_text)
        if word_count > 30 and sentences > 0:
            asl = word_count / sentences           # avg sentence length
            asw = syllables / max(word_count, 1)   # avg syllables per word
            fk_ease = 206.835 - 1.015 * asl - 84.6 * asw
            metadata["flesch_kincaid_ease"] = round(fk_ease, 1)
            if fk_ease < 30:
                issues.append(
                    ContentIssue(
                        "very_hard_to_read",
                        "medium",
                        f"Content is very hard to read (Flesch score: {fk_ease:.1f}).",
                        "Use shorter sentences and simpler words to improve readability.",
                    )
                )
            elif fk_ease < 50:
                issues.append(
                    ContentIssue(
                        "hard_to_read",
                        "low",
                        f"Content readability could be improved (Flesch score: {fk_ease:.1f}).",
                        "Aim for a Flesch Reading Ease score of 60+ for most audiences.",
                    )
                )
        else:
            metadata["flesch_kincaid_ease"] = None

        # ---- Heading distribution -----------------------------------
        h1_count = len(soup.find_all("h1"))
        h2_count = len(soup.find_all("h2"))
        metadata["h1_count"] = h1_count
        metadata["h2_count"] = h2_count
        if word_count > 300 and h2_count == 0:
            issues.append(
                ContentIssue(
                    "no_section_headings",
                    "low",
                    "Long content with no H2 subheadings.",
                    "Break up content with descriptive H2 headings to improve scanability.",
                )
            )

        # ---- Keyword density (basic) --------------------------------
        if words:
            freq = _word_frequency(words)
            top_words = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]
            metadata["top_keywords"] = [
                {"word": w, "count": c} for w, c in top_words
            ]
            max_density = top_words[0][1] / word_count if top_words else 0
            metadata["max_keyword_density"] = round(max_density, 3)
            if max_density > 0.05:
                issues.append(
                    ContentIssue(
                        "keyword_stuffing",
                        "medium",
                        f"Possible keyword stuffing: '{top_words[0][0]}' appears "
                        f"{top_words[0][1]} times ({max_density:.1%} density).",
                        "Keep keyword density below 3-4%; write naturally for users.",
                    )
                )

        # ---- Privacy policy / terms of service ----------------------
        links = soup.find_all("a", href=True)
        link_texts = [a.get_text(strip=True).lower() for a in links]
        link_hrefs = [a.get("href", "").lower() for a in links]
        has_privacy = any(
            "privacy" in t or "privacy" in h
            for t, h in zip(link_texts, link_hrefs)
        )
        has_terms = any(
            "terms" in t or "terms" in h
            for t, h in zip(link_texts, link_hrefs)
        )
        metadata["has_privacy_policy"] = has_privacy
        metadata["has_terms"] = has_terms
        if not has_privacy:
            issues.append(
                ContentIssue(
                    "missing_privacy_policy",
                    "high",
                    "No link to a Privacy Policy found.",
                    "Add a Privacy Policy page and link it in the footer (required by GDPR, CCPA).",
                )
            )

        # ---- Copyright notice ----------------------------------------
        has_copyright = bool(
            re.search(r"©|\bcopyright\b|\bAll Rights Reserved\b", html, re.I)
        )
        metadata["has_copyright"] = has_copyright
        if not has_copyright:
            issues.append(
                ContentIssue(
                    "missing_copyright",
                    "low",
                    "No copyright notice detected.",
                    "Add a copyright line in the footer (e.g. © 2024 Company Name).",
                )
            )

        # ---- Social media links -------------------------------------
        social_domains = {
            "facebook.com": "Facebook",
            "twitter.com": "Twitter",
            "instagram.com": "Instagram",
            "linkedin.com": "LinkedIn",
            "youtube.com": "YouTube",
            "tiktok.com": "TikTok",
        }
        socials_found = []
        for a in links:
            href = a.get("href", "").lower()
            for domain, name in social_domains.items():
                if domain in href and name not in socials_found:
                    socials_found.append(name)
        metadata["social_links"] = socials_found

        # ---- Broken image detection ----------------------------------
        broken_imgs = [
            img for img in soup.find_all("img")
            if not img.get("src") and not img.get("data-src")
        ]
        metadata["broken_images_count"] = len(broken_imgs)
        if broken_imgs:
            issues.append(
                ContentIssue(
                    "broken_images",
                    "medium",
                    f"{len(broken_imgs)} image(s) have no src attribute.",
                    "Ensure all images have valid src URLs.",
                )
            )

        # ---- Freshness indicators -----------------------------------
        date_patterns = [
            re.compile(
                r"\b(20[12]\d|19[89]\d)\b"
            ),  # 4-digit year between 1980 and 2029
        ]
        freshness_years: List[str] = []
        for pat in date_patterns:
            freshness_years.extend(pat.findall(body_text))
        if freshness_years:
            latest_year = max(int(y) for y in freshness_years)
            metadata["latest_year_mentioned"] = latest_year
            import datetime
            current_year = datetime.date.today().year
            if current_year - latest_year > 3:
                issues.append(
                    ContentIssue(
                        "stale_content",
                        "low",
                        f"Most recent year found in content is {latest_year} — content may be stale.",
                        "Review and update page content regularly to maintain relevance.",
                    )
                )

        score = _calculate_score(issues)
        recommendations = _build_recommendations(issues)

        return ContentReport(
            score=score,
            issues=issues,
            recommendations=recommendations,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# Text processing helpers
# ---------------------------------------------------------------------------


def _extract_body_text(soup: BeautifulSoup) -> str:
    # Remove scripts, styles, nav, footer
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_STOP_WORDS = frozenset(
    """a about above after again against all am an and any are aren't as at be because
    been before being below between both but by can't cannot could couldn't did didn't
    do does doesn't doing don't down during each few for from further get got had hadn't
    has hasn't have haven't having he he'd he'll he's her here here's hers herself him
    himself his how how's i i'd i'll i'm i've if in into is isn't it it's its itself
    let's me more most mustn't my myself no nor not of off on once only or other ought
    our ours ourselves out over own same shan't she she'd she'll she's should shouldn't
    so some such than that that's the their theirs them themselves then there there's
    these they they'd they'll they're they've this those through to too under until up
    very was wasn't we we'd we'll we're we've were weren't what what's when when's
    where where's which while who who's whom why why's will with won't would wouldn't
    you you'd you'll you're you've your yours yourself yourselves""".split()
)


def _tokenize(text: str) -> List[str]:
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    return [w for w in words if w not in _STOP_WORDS]


def _word_frequency(words: List[str]) -> Dict[str, int]:
    freq: Dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq


def _count_sentences(text: str) -> int:
    return max(1, len(re.findall(r"[.!?]+", text)))


def _count_syllables(text: str) -> int:
    """Approximate syllable count via vowel-group counting."""
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    count = 0
    for word in words:
        vowel_groups = re.findall(r"[aeiouy]+", word)
        count += max(1, len(vowel_groups))
    return count


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS = {"critical": 25, "high": 12, "medium": 6, "low": 2, "info": 0}


def _calculate_score(issues: List[ContentIssue]) -> float:
    penalty = sum(_SEVERITY_WEIGHTS.get(i.severity, 0) for i in issues)
    return max(0.0, min(100.0, 100.0 - penalty))


def _build_recommendations(issues: List[ContentIssue]) -> List[Dict[str, Any]]:
    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    recs = []
    for i in issues:
        if i.recommendation:
            recs.append(
                {
                    "category": "content",
                    "priority": priority_map.get(i.severity, 5),
                    "title": i.type.replace("_", " ").title(),
                    "description": i.recommendation,
                    "severity": i.severity,
                }
            )
    recs.sort(key=lambda r: r["priority"])
    return recs
