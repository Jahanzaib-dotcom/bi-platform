"""Freelance platforms client & hiring project discovery provider.

Discovers active employers and paying clients on Upwork, Freelancer.com,
and Fiverr who are actively hiring web developers, Shopify experts,
WordPress designers, and e-commerce specialists.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import urllib.request
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import quote, urlparse

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)


def generate_freelance_proposal(
    title: str,
    description: str,
    platform: str,
    budget: Optional[str] = None,
) -> str:
    """Crafts an authentic, high-converting proposal pitch tailored to the client's job."""
    clean_title = re.sub(r"\s*-\s*Freelance Job.*$", "", title, flags=re.IGNORECASE).strip()
    clean_title = re.sub(r"^Client:\s*", "", clean_title, flags=re.IGNORECASE).strip()

    budget_mention = f" I noticed your budget of {budget} and can comfortably deliver within that range." if budget else ""

    pitch = (
        f"Hi there! Saw your project '{clean_title}' on {platform.title()}.{budget_mention}\n\n"
        f"I specialize in building sleek, high-performing websites and e-commerce storefronts tailored to client goals. "
        f"Here is how I would approach your project:\n"
        f"1. Fast Discovery & Scope: Confirm all design preferences, brand assets, and technical needs upfront.\n"
        f"2. Mobile-First Development: Clean, modern layout optimized for fast load speeds, conversions, and SEO.\n"
        f"3. Interactive Milestone Preview: You get a working preview within 48-72 hours to test and review.\n"
        f"4. Launch & Handoff: Full testing, domain linking, and 30 days of complimentary post-launch support.\n\n"
        f"I've delivered similar projects on time with 5-star ratings. Would love to discuss your timeline or share a quick live demo. When is a good time for a quick chat?"
    )
    return pitch


class FreelanceProvider(BaseDiscoveryProvider):
    """Discovers hiring clients and projects from Upwork, Freelancer.com, and Fiverr."""

    _RATE_LIMIT_RPM = 20

    @property
    def provider_name(self) -> str:
        return "freelance"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        return {
            "provider": "freelance",
            "healthy": True,
            "message": "OK (Upwork & Freelancer.com live feeds)",
        }

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        seen_urls: set[str] = set()
        yielded = 0
        target = query.strip() if query else (industry or "website design")

        # 1. Fetch live projects from Freelancer.com Public API
        fl_results = await self._fetch_freelancer_api(target, max_results=max_results)
        for item in fl_results:
            if yielded >= max_results:
                break
            url = item.raw_data.get("project_url")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)

            yield item
            yielded += 1
            await asyncio.sleep(0.02)

        # 2. Mine Upwork live job listings
        if yielded < max_results:
            uw_results = await self._search_upwork_jobs(target, max_results=(max_results - yielded))
            for item in uw_results:
                if yielded >= max_results:
                    break
                url = item.raw_data.get("project_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                yield item
                yielded += 1
                await asyncio.sleep(0.02)

        # 3. Mine Fiverr buyer requests & project searches if needed
        if yielded < max_results:
            fiverr_results = await self._search_fiverr_jobs(target, max_results=(max_results - yielded))
            for item in fiverr_results:
                if yielded >= max_results:
                    break
                url = item.raw_data.get("project_url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)

                yield item
                yielded += 1
                await asyncio.sleep(0.02)

    async def _fetch_freelancer_api(self, query: str, max_results: int = 50) -> List[BusinessResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_fetch_freelancer, query, max_results)

    @staticmethod
    def _sync_fetch_freelancer(query: str, max_results: int) -> List[BusinessResult]:
        results: List[BusinessResult] = []
        try:
            q_enc = quote(query)
            limit = min(50, max(10, max_results))
            url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?query={q_enc}&limit={limit}&compact=true"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))

            projects = data.get("result", {}).get("projects", [])
            for p in projects:
                title = p.get("title", "").strip()
                if not title or len(title) < 5:
                    continue

                seo_url = p.get("seo_url") or str(p.get("id"))
                project_url = f"https://www.freelancer.com/projects/{seo_url}"

                desc = (p.get("preview_description") or p.get("description") or "").strip()
                budget_obj = p.get("budget", {})
                min_b = budget_obj.get("minimum")
                max_b = budget_obj.get("maximum")
                curr = budget_obj.get("currency", {}).get("code") or "USD"

                budget_str = None
                if min_b is not None and max_b is not None:
                    budget_str = f"${int(min_b)} - ${int(max_b)} {curr}"
                elif max_b is not None:
                    budget_str = f"Up to ${int(max_b)} {curr}"

                pitch = generate_freelance_proposal(
                    title=title,
                    description=desc,
                    platform="Freelancer.com",
                    budget=budget_str,
                )

                raw_data = {
                    "platform": "freelancer",
                    "project_url": project_url,
                    "budget": budget_str,
                    "job_description": desc,
                    "pitch": pitch,
                    "source_provider": "freelancer",
                    "has_website": False,
                }

                results.append(
                    BusinessResult(
                        name=f"Client: {title}",
                        address=None,
                        city=None,
                        state=None,
                        country=None,
                        phone=None,
                        email=None,
                        website_url=None,  # No website! They are hiring to build one
                        category="Freelance / Client Project",
                        source="freelancer",
                        source_id=str(p.get("id") or seo_url),
                        raw_data=raw_data,
                    )
                )
        except Exception as exc:
            logger.warning("Freelancer API error for %r: %s", query, exc)

        return results

    async def _search_upwork_jobs(self, query: str, max_results: int = 50) -> List[BusinessResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search_upwork, query, max_results)

    @staticmethod
    def _sync_search_upwork(query: str, max_results: int) -> List[BusinessResult]:
        results: List[BusinessResult] = []
        try:
            from ddgs import DDGS

            search_queries = [
                f'site:upwork.com/freelance-jobs/apply/ "{query}"',
                f'site:upwork.com/freelance-jobs/ "{query}" "Hourly" OR "Budget"',
                f'site:upwork.com/jobs/ "{query}"',
            ]

            with DDGS() as ddgs:
                for sq in search_queries:
                    if len(results) >= max_results:
                        break
                    raw = list(ddgs.text(sq, max_results=min(25, max_results)))
                    for r in raw:
                        href = r.get("href") or r.get("url") or ""
                        parsed = urlparse(href)
                        if "upwork.com" not in parsed.netloc.lower():
                            continue
                        if not any(k in parsed.path for k in ("/apply/", "/freelance-jobs/", "/jobs/")):
                            continue
                        if parsed.path.strip("/") in ("freelance-jobs", "jobs", "freelance-jobs/online"):
                            continue

                        title = r.get("title", "").strip()
                        clean_title = re.sub(r"\s*-\s*Freelance Job.*$", "", title, flags=re.IGNORECASE).strip()
                        clean_title = re.sub(r"\s*\|\s*Upwork.*$", "", clean_title, flags=re.IGNORECASE).strip()
                        if not clean_title or len(clean_title) < 5 or clean_title.lower() in ("upwork", "freelance jobs"):
                            continue

                        body = r.get("body") or r.get("snippet") or ""

                        # Extract potential budget string from snippet
                        m_budget = re.search(r"(\$\d+(?:,\d+)*(?:\s*-\s*\$\d+(?:,\d+)*)?(?:\s*/\s*hr)?)", body)
                        budget_str = m_budget.group(1) if m_budget else None

                        pitch = generate_freelance_proposal(
                            title=clean_title,
                            description=body,
                            platform="Upwork",
                            budget=budget_str,
                        )

                        raw_data = {
                            "platform": "upwork",
                            "project_url": href,
                            "budget": budget_str,
                            "job_description": body,
                            "pitch": pitch,
                            "source_provider": "upwork",
                            "has_website": False,
                        }

                        results.append(
                            BusinessResult(
                                name=f"Client: {clean_title}",
                                address=None,
                                city=None,
                                state=None,
                                country=None,
                                phone=None,
                                email=None,
                                website_url=None,
                                category="Freelance / Client Project",
                                source="upwork",
                                source_id=href.split("/")[-1] or clean_title,
                                raw_data=raw_data,
                            )
                        )
        except Exception as exc:
            logger.warning("Upwork search error for %r: %s", query, exc)

        return results

    async def _search_fiverr_jobs(self, query: str, max_results: int = 25) -> List[BusinessResult]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search_fiverr, query, max_results)

    @staticmethod
    def _sync_search_fiverr(query: str, max_results: int) -> List[BusinessResult]:
        results: List[BusinessResult] = []
        try:
            from ddgs import DDGS

            search_query = f'site:fiverr.com "looking for" "{query}"'
            with DDGS() as ddgs:
                raw = list(ddgs.text(search_query, max_results=min(20, max_results)))
                for r in raw:
                    href = r.get("href") or ""
                    if "fiverr.com" not in href.lower():
                        continue
                    title = r.get("title", "").strip()
                    clean_title = re.sub(r"\s*\|\s*Fiverr.*$", "", title, flags=re.IGNORECASE).strip()
                    if not clean_title or len(clean_title) < 5:
                        continue
                    body = r.get("body") or ""

                    pitch = generate_freelance_proposal(
                        title=clean_title,
                        description=body,
                        platform="Fiverr",
                    )

                    raw_data = {
                        "platform": "fiverr",
                        "project_url": href,
                        "budget": None,
                        "job_description": body,
                        "pitch": pitch,
                        "source_provider": "fiverr",
                        "has_website": False,
                    }

                    results.append(
                        BusinessResult(
                            name=f"Client: {clean_title}",
                            address=None,
                            city=None,
                            state=None,
                            country=None,
                            phone=None,
                            email=None,
                            website_url=None,
                            category="Freelance / Client Project",
                            source="fiverr",
                            source_id=href,
                            raw_data=raw_data,
                        )
                    )
        except Exception as exc:
            logger.warning("Fiverr search error for %r: %s", query, exc)

        return results
