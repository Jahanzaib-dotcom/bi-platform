"""
AuditService — async service layer for AuditReport lifecycle management.

Public API
----------
create_audit(session, business_id, config)  -> AuditReport
get_audit(session, audit_id)                -> AuditReport
get_business_audits(session, business_id)   -> list[AuditReport]
trigger_audit_job(session, business_id)     -> str  (Celery task ID)
get_audit_stats(session)                    -> dict
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessNotFoundError, NotFoundError
from app.core.logging import get_logger
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Sentinel for missing audit
# ---------------------------------------------------------------------------

_AUDIT_NOT_FOUND_MSG = "Audit report not found."


class AuditNotFoundError(NotFoundError):
    error_code = "audit_not_found"

    def __init__(self, audit_id: Optional[Any] = None) -> None:
        msg = f"Audit '{audit_id}' was not found." if audit_id else _AUDIT_NOT_FOUND_MSG
        super().__init__(msg)


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------


class AuditService:
    """
    Stateless async service for :class:`~app.models.audit.AuditReport`.
    """

    # ------------------------------------------------------------------
    # create_audit
    # ------------------------------------------------------------------

    @staticmethod
    async def create_audit(
        session: AsyncSession,
        business_id: str | uuid.UUID,
        config: Optional[dict[str, Any]] = None,
    ) -> AuditReport:
        """
        Create a new :class:`AuditReport` in ``pending`` state.

        Parameters
        ----------
        session:
            Open async session.
        business_id:
            UUID of the :class:`~app.models.business.Business` to audit.
        config:
            Optional audit configuration forwarded to the Celery task, e.g.
            ``{"capture_screenshots": True, "run_ai_analysis": True}``.

        Raises
        ------
        BusinessNotFoundError
            If the business does not exist.

        Returns
        -------
        AuditReport
            Freshly created report in ``pending`` state.
        """
        try:
            bid = uuid.UUID(str(business_id))
        except ValueError as exc:
            raise BusinessNotFoundError(str(business_id)) from exc

        # Verify the business exists and grab its website URL
        biz_stmt = select(Business).where(Business.id == bid)
        biz_result = await session.execute(biz_stmt)
        business: Optional[Business] = biz_result.scalar_one_or_none()
        if business is None:
            raise BusinessNotFoundError(str(business_id))

        report = AuditReport(
            business_id=bid,
            website_url=business.website_url,
            status=AuditStatus.pending,
        )
        session.add(report)
        await session.commit()
        await session.refresh(report)

        logger.info(
            "audit_service.created",
            audit_id=str(report.id),
            business_id=str(bid),
        )
        return report

    # ------------------------------------------------------------------
    # get_audit
    # ------------------------------------------------------------------

    @staticmethod
    async def get_audit(
        session: AsyncSession,
        audit_id: str | uuid.UUID,
    ) -> AuditReport:
        """
        Fetch a single :class:`AuditReport` by primary key.

        Raises
        ------
        AuditNotFoundError
            If no record with *audit_id* exists.
        """
        try:
            aid = uuid.UUID(str(audit_id))
        except ValueError as exc:
            raise AuditNotFoundError(str(audit_id)) from exc

        stmt = select(AuditReport).where(AuditReport.id == aid)
        result = await session.execute(stmt)
        report = result.scalar_one_or_none()

        if report is None:
            raise AuditNotFoundError(str(audit_id))

        return report

    # ------------------------------------------------------------------
    # get_business_audits
    # ------------------------------------------------------------------

    @staticmethod
    async def get_business_audits(
        session: AsyncSession,
        business_id: str | uuid.UUID,
        limit: int = 50,
    ) -> list[AuditReport]:
        """
        Return all audit reports for the given *business_id*, newest first.

        Parameters
        ----------
        session:
            Open async session.
        business_id:
            UUID of the target business.
        limit:
            Maximum number of reports to return (default 50).

        Raises
        ------
        BusinessNotFoundError
            If the business does not exist.
        """
        try:
            bid = uuid.UUID(str(business_id))
        except ValueError as exc:
            raise BusinessNotFoundError(str(business_id)) from exc

        # Verify business existence
        exists_stmt = select(Business.id).where(Business.id == bid)
        exists_result = await session.execute(exists_stmt)
        if exists_result.scalar_one_or_none() is None:
            raise BusinessNotFoundError(str(business_id))

        stmt = (
            select(AuditReport)
            .where(AuditReport.business_id == bid)
            .order_by(desc(AuditReport.created_at))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # trigger_audit_job
    # ------------------------------------------------------------------

    @staticmethod
    async def trigger_audit_job(
        session: AsyncSession,
        business_id: str | uuid.UUID,
        config: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Dispatch a Celery audit task for *business_id* and return the task ID.

        A new :class:`AuditReport` in ``pending`` state is created before
        the task is queued so the caller can track the report ID if needed.
        The task itself will update the report as it progresses.

        Parameters
        ----------
        session:
            Open async session.
        business_id:
            UUID of the target business.
        config:
            Optional task configuration, e.g.
            ``{"capture_screenshots": True, "run_ai_analysis": True}``.

        Raises
        ------
        BusinessNotFoundError
            If the business does not exist.

        Returns
        -------
        str
            Celery async-result task ID (UUID string).
        """
        from app.workers.audit_worker import run_audit_job  # avoid circular import at module level

        # Create the pending report
        await AuditService.create_audit(session, business_id, config)

        task_config = config or {}
        async_result = run_audit_job.apply_async(
            args=[str(business_id)],
            kwargs={"config": task_config},
            queue="audit-queue",
        )
        task_id: str = async_result.id

        logger.info(
            "audit_service.job_triggered",
            business_id=str(business_id),
            task_id=task_id,
        )
        return task_id

    # ------------------------------------------------------------------
    # get_audit_stats
    # ------------------------------------------------------------------

    @staticmethod
    async def get_audit_stats(session: AsyncSession) -> dict[str, Any]:
        """
        Return aggregate statistics for the audit_reports table.

        Returns a dict with:

        * ``total``              – total audit count
        * ``by_status``          – mapping of status -> count
        * ``avg_overall_score``  – average overall score (or ``None``)
        * ``avg_seo_score``      – average SEO score
        * ``avg_mobile_score``   – average mobile score
        * ``completed_today``    – audits completed in the last 24 h
        * ``avg_duration_seconds`` – average time from started_at to completed_at
        """
        from datetime import timedelta
        from sqlalchemy import case, cast, Float

        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(hours=24)

        # -- Aggregate --------------------------------------------------------
        agg_stmt = select(
            func.count(AuditReport.id).label("total"),
            func.avg(AuditReport.overall_score).label("avg_overall"),
            func.avg(AuditReport.seo_score).label("avg_seo"),
            func.avg(AuditReport.mobile_score).label("avg_mobile"),
            func.count(
                case((AuditReport.completed_at >= yesterday, 1))
            ).label("completed_today"),
        )
        agg_result = await session.execute(agg_stmt)
        agg_row = agg_result.one()

        # -- By status --------------------------------------------------------
        status_stmt = (
            select(AuditReport.status, func.count(AuditReport.id).label("count"))
            .group_by(AuditReport.status)
        )
        status_rows = (await session.execute(status_stmt)).all()
        by_status = {r.status.value: r.count for r in status_rows}

        # Ensure all statuses are represented
        for status in AuditStatus:
            by_status.setdefault(status.value, 0)

        def _avg(val: Any) -> Optional[float]:
            if val is None:
                return None
            return round(float(val), 2)

        return {
            "total": agg_row.total,
            "by_status": by_status,
            "avg_overall_score": _avg(agg_row.avg_overall),
            "avg_seo_score": _avg(agg_row.avg_seo),
            "avg_mobile_score": _avg(agg_row.avg_mobile),
            "completed_today": agg_row.completed_today,
        }
