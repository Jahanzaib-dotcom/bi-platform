"""
DiscoveryService — async service layer for DiscoveryJob management.

Public API
----------
create_job(session, config, user_id)              -> DiscoveryJob
get_job(session, job_id)                          -> DiscoveryJob
list_jobs(session, user_id, status, limit)        -> list[DiscoveryJob]
update_job_status(session, job_id, status, progress)
start_job(session, job_id)                        -> str  (Celery task ID)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.discovery_job import DiscoveryJob, JobStatus

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# DiscoveryJobNotFoundError
# ---------------------------------------------------------------------------


class DiscoveryJobNotFoundError(NotFoundError):
    error_code = "discovery_job_not_found"

    def __init__(self, job_id: Optional[Any] = None) -> None:
        msg = f"Discovery job '{job_id}' was not found." if job_id else "Discovery job not found."
        super().__init__(msg)


# ---------------------------------------------------------------------------
# DiscoveryService
# ---------------------------------------------------------------------------


class DiscoveryService:
    """
    Stateless async service for :class:`~app.models.discovery_job.DiscoveryJob`.
    """

    # ------------------------------------------------------------------
    # create_job
    # ------------------------------------------------------------------

    @staticmethod
    async def create_job(
        session: AsyncSession,
        config: dict[str, Any],
        user_id: str | uuid.UUID,
    ) -> DiscoveryJob:
        """
        Create and persist a new :class:`DiscoveryJob` in ``pending`` state.

        Parameters
        ----------
        session:
            Open async session.
        config:
            Discovery configuration.  Expected keys (all optional):

            * ``keywords``    – search query string
            * ``country``     – ISO-3166-1 alpha-2 country code
            * ``city``        – target city name
            * ``industry``    – target industry
            * ``sources``     – list of provider names (default ``["duckduckgo"]``)
            * ``max_results`` – upper bound on discovered records (default 100)
        user_id:
            UUID of the user who owns this job.

        Returns
        -------
        DiscoveryJob
            Freshly created job in ``pending`` state.
        """
        try:
            uid = uuid.UUID(str(user_id))
        except ValueError as exc:
            raise ValueError(f"Invalid user_id: {user_id}") from exc

        # Derive a human-readable job name from config
        parts = filter(None, [
            config.get("keywords"),
            config.get("industry"),
            config.get("city"),
            config.get("country"),
        ])
        name = " | ".join(parts) or "Discovery Job"
        name = name[:250]  # guard DB column limit

        job = DiscoveryJob(
            user_id=uid,
            name=name,
            status=JobStatus.pending,
            config=config,
            total_found=0,
            total_processed=0,
            total_errors=0,
            logs=[],
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)

        logger.info(
            "discovery_service.job_created",
            job_id=str(job.id),
            user_id=str(uid),
            name=name,
        )
        return job

    # ------------------------------------------------------------------
    # get_job
    # ------------------------------------------------------------------

    @staticmethod
    async def get_job(
        session: AsyncSession,
        job_id: str | uuid.UUID,
    ) -> DiscoveryJob:
        """
        Fetch a :class:`DiscoveryJob` by primary key.

        Raises
        ------
        DiscoveryJobNotFoundError
            If no record with *job_id* exists.
        """
        try:
            jid = uuid.UUID(str(job_id))
        except ValueError as exc:
            raise DiscoveryJobNotFoundError(str(job_id)) from exc

        stmt = select(DiscoveryJob).where(DiscoveryJob.id == jid)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            raise DiscoveryJobNotFoundError(str(job_id))

        return job

    # ------------------------------------------------------------------
    # list_jobs
    # ------------------------------------------------------------------

    @staticmethod
    async def list_jobs(
        session: AsyncSession,
        user_id: Optional[str | uuid.UUID] = None,
        status: Optional[JobStatus] = None,
        limit: int = 50,
    ) -> list[DiscoveryJob]:
        """
        List :class:`DiscoveryJob` records, optionally filtered.

        Parameters
        ----------
        session:
            Open async session.
        user_id:
            If provided, return only jobs owned by this user.
        status:
            If provided, filter by :class:`~app.models.discovery_job.JobStatus`.
        limit:
            Maximum number of jobs to return, newest first (default 50).

        Returns
        -------
        list[DiscoveryJob]
            Matching jobs ordered by ``created_at DESC``.
        """
        stmt = select(DiscoveryJob).order_by(desc(DiscoveryJob.created_at)).limit(limit)

        if user_id is not None:
            try:
                uid = uuid.UUID(str(user_id))
            except ValueError:
                return []
            stmt = stmt.where(DiscoveryJob.user_id == uid)

        if status is not None:
            stmt = stmt.where(DiscoveryJob.status == status)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # update_job_status
    # ------------------------------------------------------------------

    @staticmethod
    async def update_job_status(
        session: AsyncSession,
        job_id: str | uuid.UUID,
        status: JobStatus,
        progress: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Update the ``status`` (and optionally progress counters) of a job.

        Parameters
        ----------
        session:
            Open async session.
        job_id:
            UUID of the target :class:`DiscoveryJob`.
        status:
            New :class:`~app.models.discovery_job.JobStatus` value.
        progress:
            Optional dict with any of:

            * ``total_found``     – int
            * ``total_processed`` – int
            * ``total_errors``    – int
            * ``log_message``     – str appended to the ``logs`` JSON array

        Raises
        ------
        DiscoveryJobNotFoundError
            If the job does not exist.
        """
        try:
            jid = uuid.UUID(str(job_id))
        except ValueError as exc:
            raise DiscoveryJobNotFoundError(str(job_id)) from exc

        values: dict[str, Any] = {"status": status}

        # Timing bookkeeping
        now = datetime.now(timezone.utc)
        if status == JobStatus.running:
            values["started_at"] = now
        elif status in (JobStatus.completed, JobStatus.failed, JobStatus.cancelled):
            values["completed_at"] = now

        if progress:
            for field in ("total_found", "total_processed", "total_errors"):
                if field in progress:
                    values[field] = int(progress[field])

        await session.execute(
            update(DiscoveryJob).where(DiscoveryJob.id == jid).values(**values)
        )

        # Append to logs array if a message is provided
        if progress and progress.get("log_message"):
            # Fetch the current logs to append (required because JSON arrays
            # cannot be updated atomically in a single SQL expression across
            # both SQLite and PostgreSQL without dialect-specific syntax)
            stmt = select(DiscoveryJob.logs).where(DiscoveryJob.id == jid)
            logs_result = await session.execute(stmt)
            current_logs = logs_result.scalar_one_or_none() or []
            current_logs.append({
                "ts": now.isoformat(),
                "msg": str(progress["log_message"]),
            })
            await session.execute(
                update(DiscoveryJob)
                .where(DiscoveryJob.id == jid)
                .values(logs=current_logs)
            )

        await session.commit()

        logger.debug(
            "discovery_service.job_status_updated",
            job_id=str(job_id),
            status=status.value,
        )

    # ------------------------------------------------------------------
    # start_job
    # ------------------------------------------------------------------

    @staticmethod
    async def start_job(
        session: AsyncSession,
        job_id: str | uuid.UUID,
    ) -> str:
        """
        Dispatch the :func:`~app.workers.discovery_worker.run_discovery_job`
        Celery task for *job_id* and return the task ID.

        The job must exist and be in ``pending`` or ``paused`` state.

        Parameters
        ----------
        session:
            Open async session.
        job_id:
            UUID of the target :class:`DiscoveryJob`.

        Raises
        ------
        DiscoveryJobNotFoundError
            If the job does not exist.
        ValueError
            If the job is not in a startable state.

        Returns
        -------
        str
            Celery task ID.
        """
        from app.workers.discovery_worker import run_discovery_job  # avoid circular at module level

        job = await DiscoveryService.get_job(session, job_id)

        startable_states = {JobStatus.pending, JobStatus.paused}
        if job.status not in startable_states:
            raise ValueError(
                f"Job {job_id} cannot be started from state '{job.status.value}'. "
                f"Expected one of: {[s.value for s in startable_states]}."
            )

        async_result = run_discovery_job.apply_async(
            args=[str(job_id)],
            queue="discovery-queue",
        )
        task_id: str = async_result.id

        logger.info(
            "discovery_service.job_started",
            job_id=str(job_id),
            task_id=task_id,
        )
        return task_id
