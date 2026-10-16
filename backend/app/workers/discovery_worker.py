"""
Discovery worker tasks.

Tasks
-----
run_discovery_job(job_id)
    Load a DiscoveryJob from the DB, execute the discovery engine, persist
    results, and update progress counters.

process_discovery_result(result_id)
    Enrich a single DiscoveryResult, check for duplicate businesses, and
    create / update the Business record.

cleanup_stale_jobs()
    Periodic task: mark discovery jobs that have been "running" for > 2 h
    as failed.

worker_heartbeat()
    Periodic heartbeat ping — used by monitoring to confirm workers are alive.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from celery import Task
from celery.exceptions import MaxRetriesExceededError
from celery.utils.log import get_task_logger
from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.models.business import Business, WebsiteStatus
from app.models.discovery_job import DiscoveryJob, JobStatus
from app.models.discovery_result import DiscoveryResult, ResultStatus
from app.workers.celery_app import celery_app

logger = get_task_logger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_async(coro: Any) -> Any:
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_slug(name: str) -> str:
    """Create a URL-safe slug from a business name."""
    from python_slugify import slugify  # type: ignore

    base = slugify(name, max_length=200)
    suffix = uuid.uuid4().hex[:8]
    return f"{base}-{suffix}" if base else suffix


# ---------------------------------------------------------------------------
# Task: run_discovery_job
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.workers.discovery_worker.run_discovery_job",
    max_retries=2,
    default_retry_delay=120,
    queue="discovery-queue",
)
def run_discovery_job(self: Task, job_id: str) -> Dict[str, Any]:
    """
    Execute a full discovery run for the given *job_id*.

    Steps
    -----
    1. Load the DiscoveryJob from the database.
    2. Mark job as ``running``.
    3. Run the discovery engine according to job config (keywords, country, etc.).
    4. For each discovered business, create a DiscoveryResult row and queue
       ``process_discovery_result`` asynchronously.
    5. Update progress counters as results arrive.
    6. Mark job as ``completed`` or ``failed``.
    """
    return _run_async(_run_discovery_job_async(self, job_id))


async def _run_discovery_job_async(task: Task, job_id: str) -> Dict[str, Any]:
    from app.engines.discovery.base import BusinessResult

    async with AsyncSessionLocal() as session:
        # -- Load job --
        stmt = select(DiscoveryJob).where(DiscoveryJob.id == uuid.UUID(job_id))
        row = await session.execute(stmt)
        job: Optional[DiscoveryJob] = row.scalar_one_or_none()

        if job is None:
            logger.error("discovery_job.not_found", job_id=job_id)
            return {"status": "not_found", "job_id": job_id}

        if job.status == JobStatus.cancelled:
            logger.info("discovery_job.cancelled_skip", job_id=job_id)
            return {"status": "cancelled", "job_id": job_id}

        # -- Mark running --
        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        job.logs = job.logs or []
        job.logs.append(
            {"ts": datetime.now(timezone.utc).isoformat(), "msg": "Job started"}
        )
        await session.commit()

    config: Dict[str, Any] = job.config or {}
    keywords: str = config.get("keywords", "")
    country: Optional[str] = config.get("country")
    city: Optional[str] = config.get("city")
    industry: Optional[str] = config.get("industry")
    max_results: int = int(config.get("max_results", 100))
    sources: list = config.get("sources", ["duckduckgo"])

    total_found = 0
    total_errors = 0
    result_ids: list[str] = []

    try:
        # -- Import provider dynamically to avoid circular imports at module level --
        from app.engines.discovery.providers import get_provider  # type: ignore

        for source_name in sources:
            try:
                provider = get_provider(source_name)
            except Exception as exc:
                logger.warning(
                    "discovery_job.provider_load_failed",
                    source=source_name,
                    error=str(exc),
                )
                continue

            query = " ".join(filter(None, [keywords, industry, city, country]))
            try:
                async for biz_result in provider.discover(
                    query=query,
                    country=country,
                    industry=industry,
                    city=city,
                    max_results=max_results,
                ):
                    try:
                        result_id = await _save_discovery_result(
                            job_id=uuid.UUID(job_id),
                            biz=biz_result,
                            source=source_name,
                        )
                        result_ids.append(str(result_id))
                        total_found += 1

                        # Queue enrichment task
                        process_discovery_result.delay(str(result_id))

                        # Periodically update progress in DB
                        if total_found % 10 == 0:
                            await _update_job_progress(
                                job_id=uuid.UUID(job_id),
                                total_found=total_found,
                                total_processed=0,
                                total_errors=total_errors,
                            )
                    except Exception as exc:
                        total_errors += 1
                        logger.warning(
                            "discovery_job.result_save_error",
                            job_id=job_id,
                            error=str(exc),
                        )
            except Exception as exc:
                total_errors += 1
                logger.error(
                    "discovery_job.provider_discover_error",
                    source=source_name,
                    error=str(exc),
                )

        # -- Mark completed --
        await _finalise_job(
            job_id=uuid.UUID(job_id),
            status=JobStatus.completed,
            total_found=total_found,
            total_errors=total_errors,
            message="Job completed successfully",
        )
        logger.info(
            "discovery_job.completed",
            job_id=job_id,
            total_found=total_found,
            total_errors=total_errors,
        )
        return {
            "status": "completed",
            "job_id": job_id,
            "total_found": total_found,
            "total_errors": total_errors,
            "result_ids": result_ids,
        }

    except Exception as exc:
        logger.exception("discovery_job.failed", job_id=job_id, error=str(exc))
        await _finalise_job(
            job_id=uuid.UUID(job_id),
            status=JobStatus.failed,
            total_found=total_found,
            total_errors=total_errors + 1,
            message=str(exc),
        )
        try:
            raise task.retry(exc=exc)
        except MaxRetriesExceededError:
            return {
                "status": "failed",
                "job_id": job_id,
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Task: process_discovery_result
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    name="app.workers.discovery_worker.process_discovery_result",
    max_retries=3,
    default_retry_delay=60,
    queue="discovery-queue",
)
def process_discovery_result(self: Task, result_id: str) -> Dict[str, Any]:
    """
    Enrich a single DiscoveryResult row:
    1. Load the result.
    2. Check if a Business with the same name + city already exists.
    3. Create a new Business or update the existing one.
    4. Link the result to the business.
    5. Mark result as ``processed`` (or ``duplicate``).
    """
    return _run_async(_process_discovery_result_async(self, result_id))


async def _process_discovery_result_async(
    task: Task, result_id: str
) -> Dict[str, Any]:
    from python_slugify import slugify  # type: ignore

    async with AsyncSessionLocal() as session:
        stmt = select(DiscoveryResult).where(
            DiscoveryResult.id == uuid.UUID(result_id)
        )
        row = await session.execute(stmt)
        result: Optional[DiscoveryResult] = row.scalar_one_or_none()

        if result is None:
            logger.error("discovery_result.not_found", result_id=result_id)
            return {"status": "not_found", "result_id": result_id}

        if result.status != ResultStatus.pending:
            logger.info(
                "discovery_result.already_processed",
                result_id=result_id,
                status=result.status,
            )
            return {"status": "skipped", "result_id": result_id}

        raw: Dict[str, Any] = result.raw_data or {}
        name: str = raw.get("name", "Unknown Business")
        city: Optional[str] = raw.get("city")
        website_url: Optional[str] = raw.get("website_url")

        try:
            # -- Check for existing business (name + city dedup) --
            existing_stmt = select(Business).where(Business.name == name)
            if city:
                existing_stmt = existing_stmt.where(Business.city == city)
            existing_row = await session.execute(existing_stmt)
            existing: Optional[Business] = existing_row.scalar_one_or_none()

            is_duplicate = False
            if existing:
                # Update fields only if we have richer data
                is_duplicate = True
                if website_url and not existing.website_url:
                    existing.website_url = website_url
                    existing.has_website = True
                if raw.get("phone") and not existing.phone:
                    existing.phone = raw.get("phone")
                if raw.get("email") and not existing.email:
                    existing.email = raw.get("email")
                business_id = existing.id
            else:
                # Create new business
                slug = _make_slug(name)
                new_business = Business(
                    name=name,
                    slug=slug,
                    city=city,
                    state=raw.get("state"),
                    country=raw.get("country"),
                    address=raw.get("address"),
                    phone=raw.get("phone"),
                    email=raw.get("email"),
                    website_url=website_url,
                    has_website=bool(website_url),
                    website_status=(
                        WebsiteStatus.active if website_url else None
                    ),
                    category=raw.get("category"),
                    source=result.source,
                    source_id=result.source_id,
                    discovered_at=datetime.now(timezone.utc),
                    metadata_={"raw_source": raw},
                )
                session.add(new_business)
                await session.flush()  # get new_business.id
                business_id = new_business.id

            # -- Link result to business --
            result.business_id = business_id
            result.status = ResultStatus.duplicate if is_duplicate else ResultStatus.processed
            result.processed_at = datetime.now(timezone.utc)

            await session.commit()

            logger.info(
                "discovery_result.processed",
                result_id=result_id,
                business_id=str(business_id),
                is_duplicate=is_duplicate,
            )
            return {
                "status": "processed",
                "result_id": result_id,
                "business_id": str(business_id),
                "is_duplicate": is_duplicate,
            }

        except Exception as exc:
            await session.rollback()
            result.status = ResultStatus.failed
            await session.commit()
            logger.exception(
                "discovery_result.processing_failed",
                result_id=result_id,
                error=str(exc),
            )
            try:
                raise task.retry(exc=exc)
            except MaxRetriesExceededError:
                return {
                    "status": "failed",
                    "result_id": result_id,
                    "error": str(exc),
                }


# ---------------------------------------------------------------------------
# Periodic: cleanup_stale_jobs
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.workers.discovery_worker.cleanup_stale_jobs",
    queue="discovery-queue",
)
def cleanup_stale_jobs() -> Dict[str, Any]:
    """
    Mark as ``failed`` any DiscoveryJob that has been in ``running`` state
    for more than 2 hours without completing.
    """
    return _run_async(_cleanup_stale_jobs_async())


async def _cleanup_stale_jobs_async() -> Dict[str, Any]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    async with AsyncSessionLocal() as session:
        stmt = (
            update(DiscoveryJob)
            .where(DiscoveryJob.status == JobStatus.running)
            .where(DiscoveryJob.started_at < cutoff)
            .values(
                status=JobStatus.failed,
                error_message="Job timed out (stale worker)",
                completed_at=datetime.now(timezone.utc),
            )
        )
        result = await session.execute(stmt)
        await session.commit()
        count = result.rowcount
    logger.info("cleanup_stale_jobs.done", cleaned=count)
    return {"cleaned": count}


# ---------------------------------------------------------------------------
# Periodic: worker_heartbeat
# ---------------------------------------------------------------------------


@celery_app.task(
    name="app.workers.discovery_worker.worker_heartbeat",
    queue="default",
)
def worker_heartbeat() -> Dict[str, Any]:
    """Emit a heartbeat log line so monitoring can detect dead workers."""
    ts = datetime.now(timezone.utc).isoformat()
    logger.info("worker.heartbeat", ts=ts)
    return {"alive": True, "ts": ts}


# ---------------------------------------------------------------------------
# DB helper functions
# ---------------------------------------------------------------------------


async def _save_discovery_result(
    job_id: uuid.UUID,
    biz: Any,
    source: str,
) -> uuid.UUID:
    """Persist a raw BusinessResult as a DiscoveryResult row."""
    async with AsyncSessionLocal() as session:
        row = DiscoveryResult(
            job_id=job_id,
            source=source,
            source_id=getattr(biz, "source_id", None),
            raw_data={
                "name": biz.name,
                "address": biz.address,
                "city": biz.city,
                "state": biz.state,
                "country": biz.country,
                "phone": biz.phone,
                "email": biz.email,
                "website_url": biz.website_url,
                "category": biz.category,
                "source": biz.source,
                "source_id": biz.source_id,
                **biz.raw_data,
            },
            status=ResultStatus.pending,
        )
        session.add(row)
        await session.commit()
        return row.id


async def _update_job_progress(
    job_id: uuid.UUID,
    total_found: int,
    total_processed: int,
    total_errors: int,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(DiscoveryJob)
            .where(DiscoveryJob.id == job_id)
            .values(
                total_found=total_found,
                total_processed=total_processed,
                total_errors=total_errors,
            )
        )
        await session.commit()


async def _finalise_job(
    job_id: uuid.UUID,
    status: JobStatus,
    total_found: int,
    total_errors: int,
    message: str,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(DiscoveryJob)
            .where(DiscoveryJob.id == job_id)
            .values(
                status=status,
                total_found=total_found,
                total_errors=total_errors,
                completed_at=datetime.now(timezone.utc),
                error_message=message if status == JobStatus.failed else None,
            )
        )
        await session.commit()
