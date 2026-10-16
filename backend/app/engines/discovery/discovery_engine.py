"""Main DiscoveryEngine that orchestrates all providers."""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Type

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.discovery.base import BaseDiscoveryProvider, BusinessResult
from app.engines.discovery.deduplication import BusinessDeduplicator
from app.engines.discovery.providers.duckduckgo_provider import DuckDuckGoProvider
from app.engines.discovery.providers.nominatim_provider import NominatimProvider
from app.engines.discovery.providers.overpass_provider import OverpassProvider
from app.engines.discovery.providers.serpapi_provider import SerpAPIProvider
from app.engines.discovery.providers.web_search_provider import WebSearchProvider
from app.engines.discovery.providers.instagram_provider import InstagramProvider
from app.engines.discovery.providers.facebook_provider import FacebookProvider
from app.engines.discovery.providers.reddit_provider import RedditProvider
from app.engines.discovery.providers.ecommerce_provider import EcommerceProvider
from app.engines.discovery.providers.freelance_provider import FreelanceProvider
from app.models.discovery_job import DiscoveryJob, JobStatus

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryConfig:
    """Configuration for a single discovery run."""

    # Which provider slugs to use.  Empty = use all available.
    sources: List[str] = field(default_factory=list)

    # Filters applied to every provider
    countries: List[str] = field(default_factory=list)
    industries: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

    # Per-provider limit; total may be up to len(sources) * max_results
    max_results: int = 100

    # Multiply each provider's natural rate limit by this factor (0 < x <= 1)
    rate_limit_multiplier: float = 1.0

    # Optional city filter (applied to all providers)
    city: Optional[str] = None


# Registry of all built-in providers (slug -> class).
# Overpass is PRIMARY — it runs first and is the default source.
# Nominatim is kept for explicit selection but not in the default set.
# DuckDuckGo self-skips unless DDGS_ENRICHMENT_ENABLED=true.
_PROVIDER_REGISTRY: Dict[str, Type[BaseDiscoveryProvider]] = {
    "overpass": OverpassProvider,
    "duckduckgo": DuckDuckGoProvider,
    "nominatim": NominatimProvider,
    "serpapi": SerpAPIProvider,
    "web_search": WebSearchProvider,
    "instagram": InstagramProvider,
    "facebook": FacebookProvider,
    "reddit": RedditProvider,
    "ecommerce_brands": EcommerceProvider,
    "daraz": EcommerceProvider,
    "freelance": FreelanceProvider,
    "upwork": FreelanceProvider,
    "freelancer": FreelanceProvider,
    "fiverr": FreelanceProvider,
}

# Providers used when the caller does not specify sources explicitly.
_DEFAULT_SOURCES = ["overpass", "duckduckgo"]


class DiscoveryEngine:
    """
    Orchestrates multiple discovery providers, deduplicates results, and
    optionally updates job progress in the database.

    Example::

        engine = DiscoveryEngine()
        config = DiscoveryConfig(
            sources=["duckduckgo", "nominatim"],
            industries=["restaurant"],
            countries=["US"],
            city="Austin",
            max_results=50,
        )
        async for result in engine.run_discovery(config, job_id, session):
            print(result.name)
    """

    def __init__(
        self,
        extra_providers: Optional[List[BaseDiscoveryProvider]] = None,
    ) -> None:
        # Instantiate all built-in providers once
        self._providers: Dict[str, BaseDiscoveryProvider] = {
            slug: cls() for slug, cls in _PROVIDER_REGISTRY.items()
        }
        # Allow callers to inject additional providers
        if extra_providers:
            for prov in extra_providers:
                self._providers[prov.provider_name] = prov

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_available_providers(self) -> List[str]:
        """Return slugs of all registered providers."""
        return list(self._providers.keys())

    async def estimate_results(self, config: DiscoveryConfig) -> int:
        """
        Return a rough upper-bound estimate of how many results a discovery
        run with *config* is likely to produce.

        The estimate is intentionally conservative: we multiply the number of
        active providers by the per-provider ``max_results`` capped at 500 per
        combination.
        """
        providers = self._select_providers(config)
        industries = config.industries or ["general"]
        countries = config.countries or ["US"]
        combos = max(1, len(industries) * len(countries))
        per_provider = min(config.max_results, 500)
        return len(providers) * combos * per_provider

    async def run_discovery(
        self,
        config: DiscoveryConfig,
        job_id: Optional[uuid.UUID] = None,
        db_session: Optional[AsyncSession] = None,
    ) -> AsyncGenerator[BusinessResult, None]:
        """
        Fan out to all configured providers, deduplicate, and yield
        :class:`BusinessResult` objects.

        If *job_id* and *db_session* are provided the corresponding
        :class:`~app.models.discovery_job.DiscoveryJob` row is updated with
        live progress counters.

        Errors in individual providers are logged and do not stop the
        overall run.
        """
        providers = self._select_providers(config)
        if not providers:
            logger.warning("DiscoveryEngine: no providers selected – aborting")
            return

        dedup = BusinessDeduplicator(fuzzy_threshold=0.85)
        industries = config.industries if config.industries else [config.keywords[0] if config.keywords else "business"]
        countries = config.countries if config.countries else [None]
        city = config.city

        total_found = 0
        total_processed = 0
        total_errors = 0

        # Update job to running
        if job_id and db_session:
            await self._update_job(
                db_session,
                job_id,
                status=JobStatus.running,
                started_at=datetime.now(timezone.utc),
            )

        try:
            for industry in industries:
                for country in countries:
                    query = " ".join(config.keywords) if config.keywords else industry
                    tasks = [
                        self._run_provider(
                            provider=prov,
                            query=query,
                            country=country,
                            industry=industry,
                            city=city,
                            max_results=config.max_results,
                        )
                        for prov in providers
                    ]

                    # Consume all provider generators concurrently via a queue
                    queue: asyncio.Queue[Optional[BusinessResult]] = asyncio.Queue()

                    async def _producer(gen: AsyncGenerator[BusinessResult, None]) -> None:
                        try:
                            async for item in gen:
                                await queue.put(item)
                        except Exception as exc:
                            logger.error("Provider generator error: %s", exc)
                        finally:
                            await queue.put(None)  # sentinel

                    producer_tasks = [
                        asyncio.create_task(_producer(gen)) for gen in tasks
                    ]
                    remaining_sentinels = len(producer_tasks)

                    while remaining_sentinels > 0:
                        item = await queue.get()
                        if item is None:
                            remaining_sentinels -= 1
                            continue

                        total_found += 1
                        if dedup.is_duplicate(item):
                            continue

                        total_processed += 1
                        yield item

                        # Periodic DB progress update every 10 results
                        if job_id and db_session and total_processed % 10 == 0:
                            await self._update_job(
                                db_session,
                                job_id,
                                total_found=total_found,
                                total_processed=total_processed,
                                total_errors=total_errors,
                            )

                    # Ensure all producers are done
                    await asyncio.gather(*producer_tasks, return_exceptions=True)

        except Exception as exc:
            total_errors += 1
            logger.exception("DiscoveryEngine fatal error: %s", exc)
            if job_id and db_session:
                await self._update_job(
                    db_session,
                    job_id,
                    status=JobStatus.failed,
                    error_message=str(exc),
                    total_found=total_found,
                    total_processed=total_processed,
                    total_errors=total_errors,
                )
            return

        # Final progress update
        if job_id and db_session:
            await self._update_job(
                db_session,
                job_id,
                status=JobStatus.completed,
                completed_at=datetime.now(timezone.utc),
                total_found=total_found,
                total_processed=total_processed,
                total_errors=total_errors,
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _select_providers(self, config: DiscoveryConfig) -> List[BaseDiscoveryProvider]:
        """Return the list of providers to use for *config*."""
        sources = config.sources if config.sources else _DEFAULT_SOURCES
        selected = [self._providers[slug] for slug in sources if slug in self._providers]
        if not selected:
            logger.warning(
                "None of the requested sources %r are available; "
                "falling back to overpass only",
                sources,
            )
            return [self._providers["overpass"]]
        return selected

    @staticmethod
    async def _run_provider(
        provider: BaseDiscoveryProvider,
        query: str,
        country: Optional[str],
        industry: Optional[str],
        city: Optional[str],
        max_results: int,
    ) -> AsyncGenerator[BusinessResult, None]:
        """
        Wrap a provider's ``discover`` call so that exceptions per provider
        are caught without affecting other providers.
        """
        try:
            valid = await provider.validate_config()
            if not valid:
                logger.info(
                    "Provider %r skipped (validate_config returned False)",
                    provider.provider_name,
                )
                return
            async for result in provider.discover(
                query=query,
                country=country,
                industry=industry,
                city=city,
                max_results=max_results,
            ):
                yield result
        except Exception as exc:
            logger.error(
                "Provider %r raised an unhandled error: %s",
                provider.provider_name,
                exc,
                exc_info=True,
            )

    @staticmethod
    async def _update_job(
        db_session: AsyncSession,
        job_id: uuid.UUID,
        **kwargs: Any,
    ) -> None:
        """
        Update the :class:`~app.models.discovery_job.DiscoveryJob` row
        identified by *job_id* with the provided keyword arguments.

        Silently logs and swallows database errors so that a DB hiccup
        never crashes the discovery run.
        """
        try:
            from sqlalchemy import update as sa_update

            from app.models.discovery_job import DiscoveryJob

            stmt = (
                sa_update(DiscoveryJob)
                .where(DiscoveryJob.id == job_id)
                .values(**kwargs)
            )
            await db_session.execute(stmt)
            await db_session.commit()
        except Exception as exc:
            logger.warning("Failed to update job %s in DB: %s", job_id, exc)
