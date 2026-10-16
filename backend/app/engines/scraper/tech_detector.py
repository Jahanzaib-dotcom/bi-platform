"""
TechStackDetector — fingerprint-based technology detection.

Inspects HTTP response headers, HTML source, and JS globals to identify:
  - CMS: WordPress, Wix, Squarespace, Shopify, Webflow, Joomla, Drupal, Ghost
  - Frameworks: React, Vue, Angular, Next.js, Nuxt.js, Svelte, jQuery, Bootstrap
  - Analytics: Google Analytics (UA/GA4), Google Tag Manager, Hotjar, Mixpanel,
               Segment, HubSpot, Facebook Pixel, Clarity
  - E-commerce: Shopify, WooCommerce, Magento, BigCommerce, Wix Stores
  - CSS frameworks: Tailwind, Bootstrap, Bulma, Foundation, Materialize
  - Hosting clues: Vercel, Netlify, AWS, Cloudflare, GitHub Pages
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class TechDetectionResult:
    """Structured output of TechStackDetector.detect()."""

    cms: Optional[str] = None
    frameworks: List[str] = field(default_factory=list)
    analytics: List[str] = field(default_factory=list)
    ecommerce: Optional[str] = None
    css_frameworks: List[str] = field(default_factory=list)
    hosting: Optional[str] = None
    javascript_libraries: List[str] = field(default_factory=list)
    detected_stack: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cms": self.cms,
            "frameworks": self.frameworks,
            "analytics": self.analytics,
            "ecommerce": self.ecommerce,
            "css_frameworks": self.css_frameworks,
            "hosting": self.hosting,
            "javascript_libraries": self.javascript_libraries,
            "detected_stack": self.detected_stack,
        }


# ---------------------------------------------------------------------------
# Fingerprint definitions
# ---------------------------------------------------------------------------

# Each entry: (technology_name, category, [regex_patterns])
# Patterns are tried against: html_lower, headers_str, scripts_joined

_FINGERPRINTS: List[tuple[str, str, List[str]]] = [
    # ---- CMS ----
    (
        "WordPress",
        "cms",
        [
            r"/wp-content/",
            r"/wp-includes/",
            r'content="WordPress',
            r"wp-json",
            r"xmlrpc\.php",
            r'name="generator" content="WordPress',
        ],
    ),
    (
        "Wix",
        "cms",
        [
            r"wixsite\.com",
            r"static\.parastorage\.com",
            r"wix\.com/lpviral",
            r'id="wixui-',
            r"X-Wix-",
        ],
    ),
    (
        "Squarespace",
        "cms",
        [
            r"squarespace\.com",
            r"squarespace-cdn\.com",
            r'generator" content="Squarespace',
            r"Static\.SQUARESPACE_CONTEXT",
            r"data-squarespace-",
        ],
    ),
    (
        "Shopify",
        "cms",
        [
            r"cdn\.shopify\.com",
            r"shopify\.com/s/",
            r"Shopify\.theme",
            r"myshopify\.com",
            r'"shopify-section"',
        ],
    ),
    (
        "Webflow",
        "cms",
        [
            r"webflow\.com",
            r"assets\.website-files\.com",
            r'generator" content="Webflow"',
            r"webflow\.js",
        ],
    ),
    (
        "Joomla",
        "cms",
        [
            r"/media/jui/",
            r'content="Joomla',
            r"/components/com_",
            r"joomla\.js",
        ],
    ),
    (
        "Drupal",
        "cms",
        [
            r'content="Drupal',
            r"drupal\.js",
            r"/sites/default/files/",
            r"drupal\.settings",
            r"Drupal\.behaviors",
        ],
    ),
    (
        "Ghost",
        "cms",
        [
            r'content="Ghost',
            r"ghost\.io",
            r"ghost/core",
            r"/ghost/api/",
        ],
    ),
    (
        "HubSpot CMS",
        "cms",
        [
            r"hs-scripts\.com",
            r"hubspot\.net",
            r"hscollectedforms\.net",
            r'data-hs-',
        ],
    ),
    # ---- Frameworks ----
    (
        "React",
        "framework",
        [
            r"react\.development\.js",
            r"react\.production\.min\.js",
            r"__react",
            r"data-reactroot",
            r"data-reactid",
            r'/_next/static/',   # Next.js also uses React
        ],
    ),
    (
        "Next.js",
        "framework",
        [
            r"/_next/static/",
            r"__NEXT_DATA__",
            r"next/dist/client",
            r"next-route-announcer",
        ],
    ),
    (
        "Vue.js",
        "framework",
        [
            r"vue\.runtime\.(development|production)\.min\.js",
            r"vue\.js",
            r"__vue__",
            r'data-v-',
            r"vuex",
        ],
    ),
    (
        "Nuxt.js",
        "framework",
        [
            r"_nuxt/",
            r"__nuxt",
            r"window\.__NUXT__",
        ],
    ),
    (
        "Angular",
        "framework",
        [
            r"ng-version=",
            r"angular\.min\.js",
            r"ng-app",
            r"window\.ng",
            r"zone\.js",
        ],
    ),
    (
        "Svelte",
        "framework",
        [
            r"__svelte",
            r"svelte/",
            r"svelte-kit",
        ],
    ),
    (
        "Gatsby",
        "framework",
        [
            r"gatsby-",
            r"window\.___gatsby",
            r"/static/gatsby-",
        ],
    ),
    (
        "Astro",
        "framework",
        [
            r"astro-island",
            r"astro:page-load",
            r"/_astro/",
        ],
    ),
    # ---- JavaScript libraries ----
    (
        "jQuery",
        "javascript_library",
        [
            r"jquery[-\.](\d+\.)+\d+",
            r"jquery\.min\.js",
            r"window\.jQuery",
            r"\$\(document\)\.ready",
        ],
    ),
    (
        "Lodash",
        "javascript_library",
        [
            r"lodash\.min\.js",
            r"window\._\s*=",
        ],
    ),
    (
        "Alpine.js",
        "javascript_library",
        [
            r"alpinejs",
            r"x-data=",
            r"x-init=",
        ],
    ),
    (
        "HTMX",
        "javascript_library",
        [
            r"htmx\.org",
            r"hx-get=",
            r"hx-post=",
        ],
    ),
    # ---- Analytics ----
    (
        "Google Analytics (UA)",
        "analytics",
        [
            r"google-analytics\.com/analytics\.js",
            r"ga\('create'",
            r"UA-\d{4,}-\d+",
        ],
    ),
    (
        "Google Analytics 4",
        "analytics",
        [
            r"googletagmanager\.com/gtag/js",
            r"gtag\('config'",
            r"G-[A-Z0-9]{8,}",
        ],
    ),
    (
        "Google Tag Manager",
        "analytics",
        [
            r"googletagmanager\.com/gtm\.js",
            r"GTM-[A-Z0-9]+",
        ],
    ),
    (
        "Hotjar",
        "analytics",
        [
            r"static\.hotjar\.com",
            r"hj\('",
            r"hjid:",
        ],
    ),
    (
        "Mixpanel",
        "analytics",
        [
            r"cdn\.mxpnl\.com",
            r"api\.mixpanel\.com",
            r"mixpanel\.init",
        ],
    ),
    (
        "Segment",
        "analytics",
        [
            r"cdn\.segment\.com",
            r"analytics\.identify",
            r"analytics\.track",
        ],
    ),
    (
        "HubSpot Analytics",
        "analytics",
        [
            r"js\.hs-scripts\.com",
            r"js\.hsleadflows\.net",
        ],
    ),
    (
        "Facebook Pixel",
        "analytics",
        [
            r"connect\.facebook\.net/en_US/fbevents\.js",
            r"fbq\('init'",
            r"fbq\('track'",
        ],
    ),
    (
        "Microsoft Clarity",
        "analytics",
        [
            r"clarity\.ms/tag",
            r"window\.clarity\(",
        ],
    ),
    (
        "Heap Analytics",
        "analytics",
        [
            r"heapanalytics\.com",
            r"heap\.load\(",
        ],
    ),
    (
        "Intercom",
        "analytics",
        [
            r"widget\.intercom\.io",
            r"Intercom\('boot'",
        ],
    ),
    (
        "Crisp Chat",
        "analytics",
        [
            r"client\.crisp\.chat",
            r"\$crisp\.push",
        ],
    ),
    # ---- E-commerce ----
    (
        "WooCommerce",
        "ecommerce",
        [
            r"woocommerce",
            r"/wc-api/",
            r"wc_add_to_cart",
        ],
    ),
    (
        "Magento",
        "ecommerce",
        [
            r"mage/",
            r"Magento_",
            r"var BLANK_URL",
            r"mage\.cookies",
        ],
    ),
    (
        "BigCommerce",
        "ecommerce",
        [
            r"bigcommerce\.com",
            r"cdn11\.bigcommerce\.com",
            r"BCData",
        ],
    ),
    (
        "PrestaShop",
        "ecommerce",
        [
            r"prestashop",
            r"/modules/prestashop",
        ],
    ),
    (
        "OpenCart",
        "ecommerce",
        [
            r"opencart",
            r"catalog/view/theme",
        ],
    ),
    # ---- CSS frameworks ----
    (
        "Bootstrap",
        "css_framework",
        [
            r"bootstrap\.min\.css",
            r"bootstrap\.css",
            r'class="[^"]*\b(container|row|col-|navbar)\b',
        ],
    ),
    (
        "Tailwind CSS",
        "css_framework",
        [
            r"tailwindcss",
            r"cdn\.tailwindcss\.com",
            r'class="[^"]*(text-\w+-\d{3}|bg-\w+-\d{3}|flex\s|grid\s)',
        ],
    ),
    (
        "Bulma",
        "css_framework",
        [
            r"bulma\.io",
            r"bulma\.min\.css",
            r'class="[^"]*\bcolumns\b',
        ],
    ),
    (
        "Foundation",
        "css_framework",
        [
            r"foundation\.min\.css",
            r"foundation\.css",
        ],
    ),
    (
        "Materialize",
        "css_framework",
        [
            r"materialize\.min\.css",
            r"materialize\.css",
        ],
    ),
    (
        "Chakra UI",
        "css_framework",
        [
            r"chakra-ui",
            r"@chakra-ui",
        ],
    ),
    (
        "Ant Design",
        "css_framework",
        [
            r"antd\.min\.css",
            r"antd/dist",
        ],
    ),
    # ---- Hosting ----
    (
        "Vercel",
        "hosting",
        [
            r"vercel\.app",
            r"\.vercel\.app",
            r"x-vercel-id",
        ],
    ),
    (
        "Netlify",
        "hosting",
        [
            r"netlify\.app",
            r"netlify\.com",
            r"x-nf-request-id",
        ],
    ),
    (
        "GitHub Pages",
        "hosting",
        [
            r"github\.io",
            r"githubusercontent\.com",
        ],
    ),
    (
        "Cloudflare",
        "hosting",
        [
            r"cf-ray",
            r"cloudflare",
            r"__cfduid",
            r"cf_chl_",
        ],
    ),
    (
        "AWS",
        "hosting",
        [
            r"amazonaws\.com",
            r"cloudfront\.net",
            r"x-amz-",
            r"x-amzn-requestid",
        ],
    ),
    (
        "Azure",
        "hosting",
        [
            r"azurewebsites\.net",
            r"azure\.com",
            r"x-ms-request-id",
        ],
    ),
    (
        "Google Cloud",
        "hosting",
        [
            r"storage\.googleapis\.com",
            r"run\.app",
            r"appspot\.com",
        ],
    ),
    (
        "Heroku",
        "hosting",
        [
            r"herokuapp\.com",
            r"herokussl\.com",
        ],
    ),
    (
        "Render",
        "hosting",
        [
            r"onrender\.com",
        ],
    ),
    (
        "Firebase",
        "hosting",
        [
            r"firebaseapp\.com",
            r"web\.app",
            r"firebase\.google\.com",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------


class TechStackDetector:
    """
    Analyse a web page's HTML and HTTP headers to fingerprint its technology
    stack.

    Usage::

        detector = TechStackDetector()
        result = detector.detect(html=page_html, headers=response_headers)
        print(result.cms, result.frameworks)
    """

    def detect(
        self,
        html: str = "",
        headers: Optional[Dict[str, str]] = None,
        scripts: Optional[List[str]] = None,
    ) -> TechDetectionResult:
        """
        Run all fingerprints against the supplied inputs.

        Parameters
        ----------
        html:
            Raw HTML source of the page (case-insensitive matching used).
        headers:
            Dict of HTTP response headers (keys and values lowercased).
        scripts:
            Optional list of ``src`` attribute values from ``<script>`` tags.

        Returns
        -------
        TechDetectionResult
        """
        headers = headers or {}
        scripts = scripts or []

        html_lower = html.lower()
        # Build a single search corpus: html + headers blob + script srcs
        headers_str = " ".join(f"{k}: {v}" for k, v in headers.items()).lower()
        scripts_str = " ".join(scripts).lower()
        corpus = f"{html_lower}\n{headers_str}\n{scripts_str}"

        result = TechDetectionResult()

        for tech_name, category, patterns in _FINGERPRINTS:
            if self._matches_any(corpus, patterns):
                self._assign(result, tech_name, category)

        # Deduplicate while preserving insertion order
        result.frameworks = list(dict.fromkeys(result.frameworks))
        result.analytics = list(dict.fromkeys(result.analytics))
        result.css_frameworks = list(dict.fromkeys(result.css_frameworks))
        result.javascript_libraries = list(dict.fromkeys(result.javascript_libraries))

        # Build flat detected_stack list for convenient serialisation
        result.detected_stack = self._build_stack(result)

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _matches_any(corpus: str, patterns: List[str]) -> bool:
        for pattern in patterns:
            if re.search(pattern, corpus, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _assign(result: TechDetectionResult, name: str, category: str) -> None:
        if category == "cms" and result.cms is None:
            result.cms = name
        elif category == "framework":
            result.frameworks.append(name)
        elif category == "analytics":
            result.analytics.append(name)
        elif category == "ecommerce" and result.ecommerce is None:
            result.ecommerce = name
        elif category == "css_framework":
            result.css_frameworks.append(name)
        elif category == "hosting" and result.hosting is None:
            result.hosting = name
        elif category == "javascript_library":
            result.javascript_libraries.append(name)

    @staticmethod
    def _build_stack(result: TechDetectionResult) -> List[Dict[str, Any]]:
        stack: List[Dict[str, Any]] = []
        if result.cms:
            stack.append({"name": result.cms, "category": "cms", "confidence": "high"})
        for fw in result.frameworks:
            stack.append({"name": fw, "category": "framework", "confidence": "high"})
        for lib in result.javascript_libraries:
            stack.append({"name": lib, "category": "javascript_library", "confidence": "medium"})
        for an in result.analytics:
            stack.append({"name": an, "category": "analytics", "confidence": "high"})
        if result.ecommerce:
            stack.append({"name": result.ecommerce, "category": "ecommerce", "confidence": "high"})
        for css in result.css_frameworks:
            stack.append({"name": css, "category": "css_framework", "confidence": "medium"})
        if result.hosting:
            stack.append({"name": result.hosting, "category": "hosting", "confidence": "medium"})
        return stack
