"""
SEOAnalyzer — static and structural SEO analysis of a web page.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SEOIssue:
    type: str                   # e.g. "missing_title", "short_description"
    severity: str               # critical | high | medium | low | info
    message: str
    recommendation: str = ""
    selector: Optional[str] = None
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class SEOReport:
    score: float
    issues: List[SEOIssue] = field(default_factory=list)
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


class SEOAnalyzer:
    """
    Perform static SEO analysis on a page's HTML.

    Usage::

        analyzer = SEOAnalyzer()
        report = await analyzer.analyze(url, html, page_data)
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    async def analyze(
        self,
        url: str,
        html: str,
        page_data: Optional[Dict[str, Any]] = None,
    ) -> SEOReport:
        """
        Parameters
        ----------
        url:
            Canonical URL of the page.
        html:
            Raw HTML body of the page.
        page_data:
            Optional dict that may carry performance metrics produced by
            PerformanceAnalyzer (e.g. ``lcp``, ``ttfb``, ``page_size_kb``).
        """
        page_data = page_data or {}
        soup = BeautifulSoup(html, "lxml")
        issues: List[SEOIssue] = []
        metadata: Dict[str, Any] = {}

        # ---- Title tag ---------------------------------------------------
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        metadata["title"] = title_text
        metadata["title_length"] = len(title_text)

        if not title_text:
            issues.append(
                SEOIssue(
                    "missing_title",
                    "critical",
                    "Page has no <title> tag.",
                    "Add a descriptive title tag (50-60 characters).",
                    selector="title",
                )
            )
        elif len(title_text) < 30:
            issues.append(
                SEOIssue(
                    "short_title",
                    "high",
                    f"Title tag is too short ({len(title_text)} chars).",
                    "Aim for 50-60 characters to maximise SERP display.",
                    selector="title",
                )
            )
        elif len(title_text) > 60:
            issues.append(
                SEOIssue(
                    "long_title",
                    "medium",
                    f"Title tag is too long ({len(title_text)} chars) and may be truncated.",
                    "Keep title under 60 characters.",
                    selector="title",
                )
            )

        # ---- Meta description --------------------------------------------
        meta_desc = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        desc_text = meta_desc.get("content", "").strip() if meta_desc else ""
        metadata["meta_description"] = desc_text
        metadata["meta_description_length"] = len(desc_text)

        if not desc_text:
            issues.append(
                SEOIssue(
                    "missing_meta_description",
                    "high",
                    "No meta description found.",
                    "Write a compelling meta description (150-160 characters).",
                )
            )
        elif len(desc_text) < 70:
            issues.append(
                SEOIssue(
                    "short_meta_description",
                    "medium",
                    f"Meta description is too short ({len(desc_text)} chars).",
                    "Aim for 150-160 characters.",
                )
            )
        elif len(desc_text) > 160:
            issues.append(
                SEOIssue(
                    "long_meta_description",
                    "low",
                    f"Meta description is too long ({len(desc_text)} chars) and may be truncated.",
                    "Keep meta description under 160 characters.",
                )
            )

        # ---- Heading hierarchy -------------------------------------------
        h1_tags = soup.find_all("h1")
        metadata["h1_count"] = len(h1_tags)
        metadata["h1_text"] = [h.get_text(strip=True) for h in h1_tags]

        if len(h1_tags) == 0:
            issues.append(
                SEOIssue(
                    "missing_h1",
                    "high",
                    "Page has no <h1> heading.",
                    "Add exactly one H1 that describes the primary topic.",
                    selector="h1",
                )
            )
        elif len(h1_tags) > 1:
            issues.append(
                SEOIssue(
                    "multiple_h1",
                    "medium",
                    f"Page has {len(h1_tags)} H1 headings; only one is recommended.",
                    "Consolidate to a single H1 per page.",
                    selector="h1",
                )
            )

        for level in range(2, 7):
            tags = soup.find_all(f"h{level}")
            metadata[f"h{level}_count"] = len(tags)

        # Check for heading hierarchy skip (e.g. H1 → H3 without H2)
        heading_levels_present = [
            lvl
            for lvl in range(1, 7)
            if soup.find(f"h{lvl}")
        ]
        for i in range(len(heading_levels_present) - 1):
            if heading_levels_present[i + 1] - heading_levels_present[i] > 1:
                issues.append(
                    SEOIssue(
                        "heading_hierarchy_skip",
                        "low",
                        (
                            f"Heading hierarchy skips from H{heading_levels_present[i]} "
                            f"to H{heading_levels_present[i+1]}."
                        ),
                        "Use sequential heading levels without gaps.",
                    )
                )

        # ---- Canonical URL -----------------------------------------------
        canonical = soup.find("link", attrs={"rel": "canonical"})
        canonical_href = canonical.get("href", "").strip() if canonical else ""
        metadata["canonical_url"] = canonical_href

        if not canonical_href:
            issues.append(
                SEOIssue(
                    "missing_canonical",
                    "medium",
                    "No canonical URL specified.",
                    "Add <link rel='canonical' href='...'> to prevent duplicate content issues.",
                )
            )

        # ---- Robots.txt --------------------------------------------------
        robots_ok = await self._check_robots_txt(url)
        metadata["robots_txt_found"] = robots_ok
        if not robots_ok:
            issues.append(
                SEOIssue(
                    "missing_robots_txt",
                    "medium",
                    "No robots.txt file detected.",
                    "Create a robots.txt to guide search engine crawlers.",
                    url=_robots_url(url),
                )
            )

        # ---- Sitemap.xml -------------------------------------------------
        sitemap_ok = await self._check_sitemap(url)
        metadata["sitemap_found"] = sitemap_ok
        if not sitemap_ok:
            issues.append(
                SEOIssue(
                    "missing_sitemap",
                    "medium",
                    "No sitemap.xml detected.",
                    "Create and submit a sitemap.xml to improve crawl coverage.",
                    url=_sitemap_url(url),
                )
            )

        # ---- Open Graph --------------------------------------------------
        og_tags = {
            tag.get("property", "").lower(): tag.get("content", "")
            for tag in soup.find_all("meta", property=re.compile(r"^og:", re.I))
        }
        metadata["open_graph"] = og_tags
        required_og = {"og:title", "og:description", "og:image"}
        missing_og = required_og - set(og_tags.keys())
        if missing_og:
            issues.append(
                SEOIssue(
                    "incomplete_open_graph",
                    "medium",
                    f"Missing Open Graph tags: {', '.join(sorted(missing_og))}.",
                    "Add og:title, og:description, and og:image for better social sharing.",
                )
            )

        # ---- Schema.org structured data ----------------------------------
        schema_scripts = soup.find_all(
            "script", attrs={"type": "application/ld+json"}
        )
        schemas_found: List[str] = []
        for script in schema_scripts:
            try:
                data = json.loads(script.string or "{}")
                schema_type = data.get("@type") or (
                    data.get("@graph", [{}])[0].get("@type", "")
                    if isinstance(data.get("@graph"), list)
                    else ""
                )
                if schema_type:
                    if isinstance(schema_type, list):
                        schemas_found.extend(schema_type)
                    else:
                        schemas_found.append(str(schema_type))
            except (json.JSONDecodeError, AttributeError):
                pass
        metadata["schema_types"] = schemas_found
        if not schemas_found:
            issues.append(
                SEOIssue(
                    "missing_structured_data",
                    "medium",
                    "No Schema.org structured data found.",
                    "Add JSON-LD structured data (LocalBusiness, Product, etc.) to enable rich snippets.",
                )
            )

        # ---- Image alt texts --------------------------------------------
        imgs = soup.find_all("img")
        imgs_total = len(imgs)
        imgs_no_alt = [
            img for img in imgs
            if not img.get("alt") and img.get("src", "").strip()
        ]
        metadata["images_total"] = imgs_total
        metadata["images_missing_alt"] = len(imgs_no_alt)

        if imgs_no_alt:
            issues.append(
                SEOIssue(
                    "images_missing_alt",
                    "high",
                    f"{len(imgs_no_alt)} image(s) are missing alt attributes.",
                    "Add descriptive alt text to all content images.",
                    selector="img:not([alt])",
                )
            )

        # ---- Internal / external links ----------------------------------
        base_domain = _extract_domain(url)
        all_links = soup.find_all("a", href=True)
        internal_links: List[str] = []
        external_links: List[str] = []
        for a in all_links:
            href = a["href"].strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_href = urllib.parse.urljoin(url, href)
            link_domain = _extract_domain(abs_href)
            if link_domain == base_domain:
                internal_links.append(abs_href)
            else:
                external_links.append(abs_href)

        metadata["internal_links_count"] = len(internal_links)
        metadata["external_links_count"] = len(external_links)

        if len(internal_links) == 0:
            issues.append(
                SEOIssue(
                    "no_internal_links",
                    "high",
                    "Page has no internal links.",
                    "Add internal links to help search engines discover other pages.",
                )
            )

        # ---- URL structure -----------------------------------------------
        parsed_url = urllib.parse.urlparse(url)
        path = parsed_url.path or "/"
        if len(path) > 100:
            issues.append(
                SEOIssue(
                    "long_url",
                    "low",
                    f"URL path is very long ({len(path)} chars).",
                    "Keep URLs short and descriptive.",
                    url=url,
                )
            )
        if re.search(r"[A-Z]", path):
            issues.append(
                SEOIssue(
                    "url_uppercase",
                    "low",
                    "URL contains uppercase letters which may cause duplicate content.",
                    "Use lowercase URLs consistently.",
                    url=url,
                )
            )
        if "_" in path:
            issues.append(
                SEOIssue(
                    "url_underscores",
                    "low",
                    "URL contains underscores; hyphens are preferred by Google.",
                    "Replace underscores with hyphens in URL paths.",
                    url=url,
                )
            )

        # ---- Mobile viewport meta ----------------------------------------
        viewport_meta = soup.find(
            "meta", attrs={"name": re.compile("^viewport$", re.I)}
        )
        metadata["has_viewport_meta"] = viewport_meta is not None
        if not viewport_meta:
            issues.append(
                SEOIssue(
                    "missing_viewport_meta",
                    "high",
                    "No viewport meta tag; page may not be mobile-friendly.",
                    "Add <meta name='viewport' content='width=device-width, initial-scale=1'>.",
                )
            )

        # ---- HTTPS -------------------------------------------------------
        if not url.startswith("https://"):
            issues.append(
                SEOIssue(
                    "not_https",
                    "critical",
                    "Page is served over HTTP, not HTTPS.",
                    "Migrate to HTTPS and redirect all HTTP traffic.",
                    url=url,
                )
            )

        # ---- Performance signals from page_data --------------------------
        lcp = page_data.get("lcp")
        if lcp and isinstance(lcp, (int, float)) and lcp > 4000:
            issues.append(
                SEOIssue(
                    "slow_lcp",
                    "high",
                    f"Largest Contentful Paint is {lcp:.0f} ms (threshold: 2500 ms).",
                    "Optimise images, server response time, and render-blocking resources.",
                )
            )

        # ---- Score calculation -------------------------------------------
        score = _calculate_seo_score(issues)
        recommendations = _build_recommendations(issues)

        return SEOReport(
            score=score,
            issues=issues,
            recommendations=recommendations,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Remote file checks
    # ------------------------------------------------------------------

    async def _check_robots_txt(self, url: str) -> bool:
        robots_url = _robots_url(url)
        return await _url_returns_200(robots_url, timeout=self._timeout)

    async def _check_sitemap(self, url: str) -> bool:
        sitemap_url = _sitemap_url(url)
        return await _url_returns_200(sitemap_url, timeout=self._timeout)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS = {
    "critical": 20,
    "high": 10,
    "medium": 5,
    "low": 2,
    "info": 0,
}


def _calculate_seo_score(issues: List[SEOIssue]) -> float:
    """Start at 100 and deduct points per issue severity."""
    penalty = sum(_SEVERITY_WEIGHTS.get(i.severity, 0) for i in issues)
    return max(0.0, min(100.0, 100.0 - penalty))


def _build_recommendations(issues: List[SEOIssue]) -> List[Dict[str, Any]]:
    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    recs = []
    for issue in issues:
        if issue.recommendation:
            recs.append(
                {
                    "category": "seo",
                    "priority": priority_map.get(issue.severity, 5),
                    "title": issue.type.replace("_", " ").title(),
                    "description": issue.recommendation,
                    "severity": issue.severity,
                }
            )
    recs.sort(key=lambda r: r["priority"])
    return recs


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _extract_domain(url: str) -> str:
    try:
        import tldextract
        ext = tldextract.extract(url)
        return f"{ext.domain}.{ext.suffix}".lower()
    except Exception:
        return urllib.parse.urlparse(url).netloc.lower().split(":")[0]


def _robots_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def _sitemap_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"


async def _url_returns_200(url: str, timeout: float = 10.0) -> bool:
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            verify=False,
            headers={"User-Agent": "BIAuditBot/1.0"},
        ) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False
