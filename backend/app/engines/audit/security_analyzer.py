"""
SecurityAnalyzer — HTTP-header and HTML-level security checks.
"""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SecurityIssue:
    type: str
    severity: str       # critical | high | medium | low | info
    message: str
    recommendation: str = ""
    reference: str = ""   # e.g. OWASP link

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v}


@dataclass
class SecurityReport:
    score: float
    issues: List[SecurityIssue] = field(default_factory=list)
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
# Security-header expectations
# ---------------------------------------------------------------------------

# (header_name, severity_if_missing, description, recommendation)
_REQUIRED_HEADERS: List[tuple] = [
    (
        "strict-transport-security",
        "critical",
        "HSTS header missing — site vulnerable to SSL-stripping attacks.",
        "Add: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
        "https://owasp.org/www-project-secure-headers/",
    ),
    (
        "content-security-policy",
        "high",
        "Content-Security-Policy header missing — XSS risk elevated.",
        "Implement a Content-Security-Policy that restricts allowed sources.",
        "https://owasp.org/www-project-secure-headers/",
    ),
    (
        "x-content-type-options",
        "medium",
        "X-Content-Type-Options header missing — MIME-sniffing risk.",
        "Add: X-Content-Type-Options: nosniff",
        "https://owasp.org/www-project-secure-headers/",
    ),
    (
        "x-frame-options",
        "medium",
        "X-Frame-Options header missing — clickjacking risk.",
        "Add: X-Frame-Options: DENY  (or use CSP frame-ancestors directive).",
        "https://owasp.org/www-project-secure-headers/",
    ),
    (
        "referrer-policy",
        "low",
        "Referrer-Policy header missing — may leak URLs to third parties.",
        "Add: Referrer-Policy: strict-origin-when-cross-origin",
        "https://owasp.org/www-project-secure-headers/",
    ),
    (
        "permissions-policy",
        "low",
        "Permissions-Policy (Feature-Policy) header missing.",
        "Restrict browser features via Permissions-Policy header.",
        "https://owasp.org/www-project-secure-headers/",
    ),
]

_DANGEROUS_HEADERS = [
    (
        "server",
        "low",
        "Server header exposes technology version info.",
        "Remove or obscure the Server response header.",
    ),
    (
        "x-powered-by",
        "low",
        "X-Powered-By header exposes technology stack info.",
        "Remove or obscure the X-Powered-By response header.",
    ),
    (
        "x-aspnet-version",
        "low",
        "X-AspNet-Version header reveals framework version.",
        "Disable X-AspNet-Version in your web.config.",
    ),
    (
        "x-aspnetmvc-version",
        "low",
        "X-AspNetMvc-Version header reveals MVC framework version.",
        "Disable X-AspNetMvc-Version in your web.config.",
    ),
]


# ---------------------------------------------------------------------------
# HTML-level security checks
# ---------------------------------------------------------------------------

# Inline event handlers that can be XSS vectors
_INLINE_EVENT_PATTERN = re.compile(
    r"\s(on(?:click|load|error|mouseover|submit|change|keyup|keydown|focus|blur))\s*=",
    re.I,
)

_HTTP_LINK_PATTERN = re.compile(r'src\s*=\s*["\']http://', re.I)
_MIXED_CONTENT_PATTERN = re.compile(
    r'(?:src|href|action)\s*=\s*["\']http://', re.I
)


# ---------------------------------------------------------------------------
# Analyser
# ---------------------------------------------------------------------------


class SecurityAnalyzer:
    """
    Perform security analysis via HTTP-header inspection and HTML heuristics.

    Parameters
    ----------
    timeout:
        HTTP client timeout in seconds.
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    async def analyze(
        self,
        url: str,
        html: str,
        response_headers: Optional[Dict[str, str]] = None,
    ) -> SecurityReport:
        """
        Parameters
        ----------
        url:
            The final URL of the page.
        html:
            Raw HTML content.
        response_headers:
            If available from a prior request, supply the response headers dict
            to avoid an extra HTTP round-trip.
        """
        issues: List[SecurityIssue] = []
        metadata: Dict[str, Any] = {"url": url}

        # ---- Fetch headers if not supplied --------------------------
        if response_headers is None:
            response_headers = await self._fetch_headers(url)
        headers_lower = {k.lower(): v for k, v in response_headers.items()}
        metadata["response_headers"] = dict(headers_lower)

        # ---- HTTPS check --------------------------------------------
        if not url.startswith("https://"):
            issues.append(
                SecurityIssue(
                    "no_https",
                    "critical",
                    "Site is not served over HTTPS.",
                    "Obtain a TLS certificate and redirect all HTTP to HTTPS.",
                    "https://letsencrypt.org",
                )
            )

        # ---- Security headers ---------------------------------------
        for header_name, severity, message, recommendation, ref in _REQUIRED_HEADERS:
            if header_name not in headers_lower:
                issues.append(
                    SecurityIssue(
                        f"missing_{header_name.replace('-', '_')}",
                        severity,
                        message,
                        recommendation,
                        ref,
                    )
                )
        metadata["security_headers_present"] = [
            h for h, *_ in _REQUIRED_HEADERS if h in headers_lower
        ]

        # ---- Information disclosure ---------------------------------
        for header_name, severity, message, recommendation in _DANGEROUS_HEADERS:
            if header_name in headers_lower:
                issues.append(
                    SecurityIssue(
                        f"info_disclosure_{header_name.replace('-', '_')}",
                        severity,
                        f"{message}  (Value: {headers_lower[header_name][:60]})",
                        recommendation,
                    )
                )

        # ---- Cookie security ----------------------------------------
        set_cookie_values = response_headers.get("set-cookie", "") or ""
        if set_cookie_values:
            metadata["has_cookies"] = True
            cookies = [c.strip() for c in set_cookie_values.split(",") if c.strip()]
            bad_cookies: List[str] = []
            for cookie in cookies:
                cookie_lower = cookie.lower()
                if "httponly" not in cookie_lower or "secure" not in cookie_lower:
                    # Grab just the name part
                    name = cookie.split("=")[0].strip()[:30]
                    bad_cookies.append(name)
            if bad_cookies:
                issues.append(
                    SecurityIssue(
                        "insecure_cookies",
                        "high",
                        f"Cookie(s) missing Secure/HttpOnly flags: {', '.join(bad_cookies[:5])}.",
                        "Set Secure and HttpOnly flags on all session/auth cookies.",
                        "https://owasp.org/www-community/controls/SecureCookieAttribute",
                    )
                )
        else:
            metadata["has_cookies"] = False

        # ---- HTML checks -------------------------------------------
        _check_html_security(html, issues, metadata)

        # ---- Mixed content ------------------------------------------
        if url.startswith("https://"):
            mixed_count = len(_MIXED_CONTENT_PATTERN.findall(html))
            metadata["mixed_content_count"] = mixed_count
            if mixed_count > 0:
                issues.append(
                    SecurityIssue(
                        "mixed_content",
                        "high",
                        f"{mixed_count} resource(s) loaded over HTTP on an HTTPS page.",
                        "Update all resource URLs to HTTPS or use protocol-relative URLs.",
                    )
                )

        score = _calculate_score(issues)
        recommendations = _build_recommendations(issues)

        return SecurityReport(
            score=score,
            issues=issues,
            recommendations=recommendations,
            metadata=metadata,
        )

    async def _fetch_headers(self, url: str) -> Dict[str, str]:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=self._timeout,
                verify=False,
                headers={"User-Agent": "BIAuditBot/1.0"},
            ) as client:
                resp = await client.head(url)
                # Some servers reject HEAD; fall back to GET
                if resp.status_code in (405, 501):
                    resp = await client.get(url)
                return dict(resp.headers)
        except Exception:
            return {}


# ---------------------------------------------------------------------------
# HTML-level security checks
# ---------------------------------------------------------------------------


def _check_html_security(
    html: str,
    issues: List[SecurityIssue],
    metadata: Dict[str, Any],
) -> None:
    # Inline event handlers (heuristic XSS indicator)
    inline_events = _INLINE_EVENT_PATTERN.findall(html)
    metadata["inline_event_handlers"] = len(inline_events)
    if len(inline_events) > 5:
        issues.append(
            SecurityIssue(
                "inline_event_handlers",
                "low",
                f"{len(inline_events)} inline event handlers detected (potential XSS surface).",
                "Move event handling to external JS files; ensure input sanitisation.",
            )
        )

    # iFrame without sandbox
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    iframes = soup.find_all("iframe")
    unsandboxed = [
        str(ifr)[:120]
        for ifr in iframes
        if not ifr.get("sandbox")
    ]
    metadata["iframes_total"] = len(iframes)
    metadata["iframes_unsandboxed"] = len(unsandboxed)
    if unsandboxed:
        issues.append(
            SecurityIssue(
                "unsandboxed_iframes",
                "medium",
                f"{len(unsandboxed)} iframe(s) have no sandbox attribute.",
                "Add sandbox attribute to all iframes: sandbox='allow-scripts allow-same-origin'.",
                "https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#sandbox",
            )
        )

    # Forms submitting over HTTP
    http_forms = [
        str(f)[:120]
        for f in soup.find_all("form")
        if re.match(r"http://", f.get("action", ""), re.I)
    ]
    if http_forms:
        issues.append(
            SecurityIssue(
                "form_http_action",
                "critical",
                f"{len(http_forms)} form(s) submit to an HTTP (non-HTTPS) endpoint.",
                "Update all form action URLs to use HTTPS.",
            )
        )

    # Detect obvious debug endpoints
    debug_patterns = re.compile(
        r"/(wp-admin|admin|phpmyadmin|adminer|debug|test|staging|phpinfo)\b",
        re.I,
    )
    debug_links = [
        a.get("href", "")
        for a in soup.find_all("a", href=debug_patterns)
    ]
    if debug_links:
        issues.append(
            SecurityIssue(
                "debug_endpoints",
                "high",
                f"Links to potentially sensitive admin/debug paths: {debug_links[:3]}.",
                "Remove public links to admin/debug interfaces and restrict access by IP.",
            )
        )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS = {"critical": 20, "high": 12, "medium": 6, "low": 2, "info": 0}


def _calculate_score(issues: List[SecurityIssue]) -> float:
    penalty = sum(_SEVERITY_WEIGHTS.get(i.severity, 0) for i in issues)
    return max(0.0, min(100.0, 100.0 - penalty))


def _build_recommendations(issues: List[SecurityIssue]) -> List[Dict[str, Any]]:
    priority_map = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}
    recs = []
    for i in issues:
        if i.recommendation:
            recs.append(
                {
                    "category": "security",
                    "priority": priority_map.get(i.severity, 5),
                    "title": i.type.replace("_", " ").title(),
                    "description": i.recommendation,
                    "severity": i.severity,
                    **({"reference": i.reference} if i.reference else {}),
                }
            )
    recs.sort(key=lambda r: r["priority"])
    return recs
