"""Reddit hiring and client lead discovery provider.

Finds verified clients, founders, and business owners actively hiring web developers,
designers, Shopify experts, and digital consultants across r/forhire, r/freelance,
r/ecommerce, r/smallbusiness, and r/entrepreneur.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urlparse

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult

logger = logging.getLogger(__name__)

SUBREDDITS = ["forhire", "freelance", "ecommerce", "smallbusiness", "entrepreneur", "webdev"]


def clean_slug_to_title(slug: str) -> str:
    """Converts a Reddit URL slug into a readable post title."""
    cleaned = re.sub(r"^[0-9a-z]+_", "", slug)  # strip possible ID prefix
    cleaned = cleaned.replace("_", " ").replace("-", " ")
    # Format tags like hiring, forhire
    cleaned = re.sub(r"\bhiring\b", "[Hiring]", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bforhire\b", "[For Hire]", cleaned, flags=re.IGNORECASE)
    return cleaned.strip().title()


class RedditProvider(BaseDiscoveryProvider):
    """Discovers high-intent client and hiring leads from top business subreddits."""

    _RATE_LIMIT_RPM = 15

    @property
    def provider_name(self) -> str:
        return "reddit"

    @property
    def rate_limit(self) -> int:
        return self._RATE_LIMIT_RPM

    async def validate_config(self) -> bool:
        return True

    async def health_check(self) -> Dict[str, Any]:
        try:
            results = await self._search("site:reddit.com/r/forhire \"[Hiring]\" website", max_results=1)
            return {
                "provider": "reddit",
                "healthy": True,
                "message": "OK",
                "sample_result_count": len(results),
            }
        except Exception as exc:
            return {"provider": "reddit", "healthy": False, "message": str(exc)}

    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        queries = self._build_queries(query, industry)
        seen_urls: set[str] = set()
        yielded = 0
        per_query = min(50, max(20, (max_results * 2) // max(1, len(queries))))

        for search_query in queries:
            if yielded >= max_results:
                break

            try:
                raw_results = await self._search(search_query, max_results=per_query)
            except Exception as exc:
                logger.warning("RedditProvider search error for %r: %s", search_query, exc)
                continue

            for item in raw_results:
                if yielded >= max_results:
                    break

                url = item.get("href") or item.get("url") or ""
                parsed = urlparse(url)
                if "reddit.com" not in parsed.netloc.lower():
                    continue

                # Ensure it's an actual post comment/thread
                if "/comments/" not in parsed.path:
                    continue

                if url in seen_urls:
                    continue
                seen_urls.add(url)

                path_parts = [p for p in parsed.path.strip("/").split("/") if p]
                # /r/<subreddit>/comments/<id>/<slug>
                subreddit = "forhire"
                slug = ""
                if len(path_parts) >= 2 and path_parts[0] == "r":
                    subreddit = path_parts[1]
                if len(path_parts) >= 5:
                    slug = path_parts[4]
                elif len(path_parts) >= 4 and path_parts[3] != "comments":
                    slug = path_parts[-1]
                elif len(path_parts) >= 2:
                    slug = path_parts[-1]

                raw_title = (item.get("title") or "").strip()
                raw_title_lower = raw_title.lower()
                slug_lower = slug.lower()

                # Strictly reject other freelancers advertising services ("for hire" / "for_hire")
                # We only want CLIENTS seeking to hire developers/services!
                if "for_hire" in slug_lower or "[for hire]" in raw_title_lower or "for hire" in raw_title_lower:
                    continue

                if "reddit.com" in raw_title.lower() or "link to" in raw_title.lower() or not raw_title:
                    title = clean_slug_to_title(slug) if slug else "Client Hiring Request"
                else:
                    title = re.sub(r"\s*:\s*r/\w+.*$", "", raw_title).strip()
                    title = re.sub(r"\s*-\s*Reddit.*$", "", title, flags=re.IGNORECASE).strip()

                # Relevance check: query keywords must be in title or slug
                if query:
                    q_words = [w.lower() for w in re.split(r"\s+", query) if len(w) >= 3]
                    if q_words:
                        text_corpus = f"{title} {slug} {item.get('body', '')}".lower()
                        if not any(w in text_corpus for w in q_words):
                            continue

                body = (item.get("body") or item.get("snippet") or "").strip()
                if "hides the web page description" in body.lower():
                    body = f"Hiring post on r/{subreddit}: {title}"

                # Extract budget if mentioned
                budget_match = re.search(r"(\$\s*[\d,]+(?:\s*-\s*\$?\s*[\d,]+)?|\b[\d,]+\s*(?:USD|EUR|GBP))", f"{title} {body}")
                budget = budget_match.group(0) if budget_match else None

                # Extract email or contact handles if present in body
                email_match = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", body)
                email = email_match.group(0).lower() if email_match else None

                discord_match = re.search(r"(?:discord(?:\.gg/|:\s*))([a-zA-Z0-9_#]+)", body, re.IGNORECASE)
                discord_handle = discord_match.group(1) if discord_match else None

                pitch = (
                    f"Hi! Saw your hiring post on r/{subreddit} regarding \"{title}\". "
                    f"I build robust, high-performance web applications and e-commerce solutions. "
                    f"I have delivered similar projects on time and within budget. "
                    f"Would love to chat or send over my relevant portfolio!"
                )

                budget_tag = f" ({budget})" if budget else ""
                lead_name = f"Client [r/{subreddit}]: {title[:55]}{budget_tag}"
                raw_data = {
                    "reddit_url": url,
                    "subreddit": f"r/{subreddit}",
                    "budget": budget,
                    "discord": discord_handle,
                    "pitch": pitch,
                    "post_snippet": body,
                    "has_website": False,
                    "source_provider": "reddit",
                }

                result = BusinessResult(
                    name=lead_name,
                    address=None,
                    city=city,
                    state=None,
                    country=country or "International",
                    phone=None,
                    email=email,
                    website_url=url,
                    category=f"Client Hiring Project (r/{subreddit})",
                    source="reddit",
                    source_id=slug or url,
                    raw_data=raw_data,
                )

                yield result
                yielded += 1
                await asyncio.sleep(0.05)

    @staticmethod
    def _build_queries(query: str, industry: Optional[str]) -> List[str]:
        target = query.strip() if query else (industry or "website")
        return [
            # Direct posts on r/forhire
            f'site:reddit.com/r/forhire {target}'.strip(),
            # Hiring posts on r/forhire
            f'site:reddit.com/r/forhire hiring {target}'.strip(),
            # Freelance subreddits
            f'site:reddit.com/r/freelance hiring {target}'.strip(),
            # Hiring_Freelancers
            f'site:reddit.com/r/Hiring_Freelancers {target}'.strip(),
        ]

    async def _search(self, query: str, max_results: int = 50) -> List[Dict[str, Any]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_search, query, max_results)

    @staticmethod
    def _sync_search(query: str, max_results: int) -> List[Dict[str, Any]]:
        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=min(max_results, 100)))
        except Exception as exc:
            logger.warning("ddgs search error for Reddit query %r: %s", query, exc)
            return []
