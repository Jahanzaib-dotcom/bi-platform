"""
AnalyticsService — optimised read-only analytics queries.

All methods issue a single SQL query (or the minimum necessary) and return
plain Python dicts / dataclasses — no lazy-loading of ORM relationships.

Public API
----------
get_dashboard_stats(session)           -> DashboardStats
get_industry_breakdown(session)        -> list[IndustryStats]
get_geo_breakdown(session, level)      -> list[dict]
get_opportunity_breakdown(session)     -> dict
get_trend_data(session, days)          -> list[TrendPoint]
get_revenue_estimates(session)         -> dict
get_score_distribution(session)        -> list[dict]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Float, case, cast, func, literal, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Return-type dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DashboardStats:
    total_businesses: int
    businesses_with_website: int
    businesses_without_website: int
    total_audits: int
    completed_audits: int
    avg_overall_score: Optional[float]
    avg_opportunity_score: Optional[float]
    new_businesses_7d: int
    new_businesses_30d: int
    audits_last_7d: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_businesses": self.total_businesses,
            "businesses_with_website": self.businesses_with_website,
            "businesses_without_website": self.businesses_without_website,
            "total_audits": self.total_audits,
            "completed_audits": self.completed_audits,
            "avg_overall_score": self.avg_overall_score,
            "avg_opportunity_score": self.avg_opportunity_score,
            "new_businesses_7d": self.new_businesses_7d,
            "new_businesses_30d": self.new_businesses_30d,
            "audits_last_7d": self.audits_last_7d,
        }


@dataclass
class IndustryStats:
    industry: str
    count: int
    with_website: int
    avg_score: Optional[float]
    avg_opportunity: Optional[float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "industry": self.industry,
            "count": self.count,
            "with_website": self.with_website,
            "avg_score": self.avg_score,
            "avg_opportunity": self.avg_opportunity,
        }


@dataclass
class TrendPoint:
    date: str  # ISO date string YYYY-MM-DD
    count: int
    cumulative: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "count": self.count,
            "cumulative": self.cumulative,
        }


# ---------------------------------------------------------------------------
# AnalyticsService
# ---------------------------------------------------------------------------


class AnalyticsService:
    """
    Read-only analytics service — all queries bypass ORM relationships for
    maximum performance.  No session writes are performed.
    """

    # ------------------------------------------------------------------
    # get_dashboard_stats
    # ------------------------------------------------------------------

    @staticmethod
    async def get_dashboard_stats(session: AsyncSession) -> DashboardStats:
        """
        Return top-level platform statistics in a single pass over the DB.
        """
        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # -- Businesses aggregate --------------------------------------------
        biz_stmt = select(
            func.count(Business.id).label("total"),
            func.count(case((Business.has_website == True, 1))).label("with_website"),
            func.count(case((Business.has_website == False, 1))).label("without_website"),
            func.avg(Business.overall_score).label("avg_score"),
            func.avg(Business.opportunity_score).label("avg_opportunity"),
            func.count(
                case((Business.discovered_at >= seven_days_ago, 1))
            ).label("new_7d"),
            func.count(
                case((Business.discovered_at >= thirty_days_ago, 1))
            ).label("new_30d"),
        )
        biz_row = (await session.execute(biz_stmt)).one()

        # -- Audits aggregate ------------------------------------------------
        audit_stmt = select(
            func.count(AuditReport.id).label("total"),
            func.count(
                case((AuditReport.status == AuditStatus.completed, 1))
            ).label("completed"),
            func.count(
                case((AuditReport.completed_at >= seven_days_ago, 1))
            ).label("last_7d"),
        )
        audit_row = (await session.execute(audit_stmt)).one()

        def _avg(val: Any) -> Optional[float]:
            return round(float(val), 2) if val is not None else None

        return DashboardStats(
            total_businesses=biz_row.total,
            businesses_with_website=biz_row.with_website,
            businesses_without_website=biz_row.without_website,
            total_audits=audit_row.total,
            completed_audits=audit_row.completed,
            avg_overall_score=_avg(biz_row.avg_score),
            avg_opportunity_score=_avg(biz_row.avg_opportunity),
            new_businesses_7d=biz_row.new_7d,
            new_businesses_30d=biz_row.new_30d,
            audits_last_7d=audit_row.last_7d,
        )

    # ------------------------------------------------------------------
    # get_industry_breakdown
    # ------------------------------------------------------------------

    @staticmethod
    async def get_industry_breakdown(
        session: AsyncSession,
        limit: int = 20,
    ) -> list[IndustryStats]:
        """
        Return per-industry aggregates ordered by business count descending.
        """
        stmt = (
            select(
                Business.industry,
                func.count(Business.id).label("count"),
                func.count(case((Business.has_website == True, 1))).label("with_website"),
                func.avg(Business.overall_score).label("avg_score"),
                func.avg(Business.opportunity_score).label("avg_opportunity"),
            )
            .where(Business.industry.isnot(None))
            .group_by(Business.industry)
            .order_by(func.count(Business.id).desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

        def _avg(val: Any) -> Optional[float]:
            return round(float(val), 2) if val is not None else None

        return [
            IndustryStats(
                industry=r.industry,
                count=r.count,
                with_website=r.with_website,
                avg_score=_avg(r.avg_score),
                avg_opportunity=_avg(r.avg_opportunity),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # get_geo_breakdown
    # ------------------------------------------------------------------

    @staticmethod
    async def get_geo_breakdown(
        session: AsyncSession,
        level: str = "country",
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """
        Return geographic distribution of businesses.

        Parameters
        ----------
        level:
            Aggregation level: ``"country"``, ``"state"``, or ``"city"``.
        limit:
            Maximum number of rows returned (default 25).

        Returns
        -------
        list[dict]
            Each item has ``{level_value, count, with_website, avg_score}``.
        """
        level = level.lower()
        if level == "state":
            group_col = Business.state
            label = "state"
        elif level == "city":
            group_col = Business.city
            label = "city"
        else:
            group_col = Business.country
            label = "country"

        stmt = (
            select(
                group_col.label(label),
                func.count(Business.id).label("count"),
                func.count(case((Business.has_website == True, 1))).label("with_website"),
                func.avg(Business.overall_score).label("avg_score"),
            )
            .where(group_col.isnot(None))
            .group_by(group_col)
            .order_by(func.count(Business.id).desc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()

        def _avg(val: Any) -> Optional[float]:
            return round(float(val), 2) if val is not None else None

        return [
            {
                label: getattr(r, label),
                "count": r.count,
                "with_website": r.with_website,
                "avg_score": _avg(r.avg_score),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # get_opportunity_breakdown
    # ------------------------------------------------------------------

    @staticmethod
    async def get_opportunity_breakdown(session: AsyncSession) -> dict[str, Any]:
        """
        Bucket businesses by opportunity tier and return counts + avg scores.

        Tiers
        -----
        * ``high``   – opportunity_score >= 70
        * ``medium`` – 40 <= opportunity_score < 70
        * ``low``    – opportunity_score < 40
        * ``unscored`` – opportunity_score IS NULL

        Returns
        -------
        dict
            ``{high, medium, low, unscored}`` each containing
            ``{count, avg_score, avg_revenue_potential}``.
        """
        stmt = select(
            # High
            func.count(case((Business.opportunity_score >= 70, 1))).label("high_count"),
            func.avg(case((Business.opportunity_score >= 70, Business.overall_score))).label("high_avg_score"),
            func.avg(case((Business.opportunity_score >= 70, Business.revenue_potential))).label("high_avg_rev"),
            # Medium
            func.count(
                case(((Business.opportunity_score >= 40) & (Business.opportunity_score < 70), 1))
            ).label("med_count"),
            func.avg(
                case(((Business.opportunity_score >= 40) & (Business.opportunity_score < 70), Business.overall_score))
            ).label("med_avg_score"),
            func.avg(
                case(((Business.opportunity_score >= 40) & (Business.opportunity_score < 70), Business.revenue_potential))
            ).label("med_avg_rev"),
            # Low
            func.count(
                case(((Business.opportunity_score.isnot(None)) & (Business.opportunity_score < 40), 1))
            ).label("low_count"),
            func.avg(
                case(((Business.opportunity_score.isnot(None)) & (Business.opportunity_score < 40), Business.overall_score))
            ).label("low_avg_score"),
            func.avg(
                case(((Business.opportunity_score.isnot(None)) & (Business.opportunity_score < 40), Business.revenue_potential))
            ).label("low_avg_rev"),
            # Unscored
            func.count(
                case((Business.opportunity_score.is_(None), 1))
            ).label("unscored_count"),
        )
        row = (await session.execute(stmt)).one()

        def _r(val: Any) -> Optional[float]:
            return round(float(val), 2) if val is not None else None

        return {
            "high": {
                "count": row.high_count,
                "avg_score": _r(row.high_avg_score),
                "avg_revenue_potential": _r(row.high_avg_rev),
            },
            "medium": {
                "count": row.med_count,
                "avg_score": _r(row.med_avg_score),
                "avg_revenue_potential": _r(row.med_avg_rev),
            },
            "low": {
                "count": row.low_count,
                "avg_score": _r(row.low_avg_score),
                "avg_revenue_potential": _r(row.low_avg_rev),
            },
            "unscored": {
                "count": row.unscored_count,
            },
        }

    # ------------------------------------------------------------------
    # get_trend_data
    # ------------------------------------------------------------------

    @staticmethod
    async def get_trend_data(
        session: AsyncSession,
        days: int = 30,
    ) -> list[TrendPoint]:
        """
        Return daily discovery counts for the last *days* days.

        Parameters
        ----------
        days:
            Lookback window in days (default 30, max 365).

        Returns
        -------
        list[TrendPoint]
            One :class:`TrendPoint` per calendar day, oldest first, with a
            running cumulative total field.
        """
        days = min(max(days, 1), 365)
        since = datetime.now(timezone.utc) - timedelta(days=days)

        # Cast discovered_at to a date so we can group by day.
        # Use a dialect-agnostic approach: cast to Date via func.date().
        date_col = func.date(Business.discovered_at).label("day")
        stmt = (
            select(
                date_col,
                func.count(Business.id).label("cnt"),
            )
            .where(Business.discovered_at >= since)
            .group_by(date_col)
            .order_by(date_col)
        )
        rows = (await session.execute(stmt)).all()

        points: list[TrendPoint] = []
        cumulative = 0
        for r in rows:
            day_str = str(r.day)
            cumulative += r.cnt
            points.append(TrendPoint(date=day_str, count=r.cnt, cumulative=cumulative))

        return points

    # ------------------------------------------------------------------
    # get_revenue_estimates
    # ------------------------------------------------------------------

    @staticmethod
    async def get_revenue_estimates(session: AsyncSession) -> dict[str, Any]:
        """
        Aggregate revenue_potential estimates across all businesses.

        Returns
        -------
        dict with:
        * ``total_estimated``   – sum of all non-null revenue_potential
        * ``avg_estimated``     – average non-null revenue_potential
        * ``max_estimated``     – maximum single-business estimate
        * ``businesses_with_estimate`` – count of non-null entries
        * ``by_industry``       – top-10 industries by total revenue_potential
        """
        agg_stmt = select(
            func.sum(Business.revenue_potential).label("total"),
            func.avg(Business.revenue_potential).label("avg"),
            func.max(Business.revenue_potential).label("max"),
            func.count(Business.revenue_potential).label("count_with"),
        ).where(Business.revenue_potential.isnot(None))
        agg_row = (await session.execute(agg_stmt)).one()

        by_industry_stmt = (
            select(
                Business.industry,
                func.sum(Business.revenue_potential).label("total"),
                func.count(Business.id).label("count"),
            )
            .where(
                Business.revenue_potential.isnot(None),
                Business.industry.isnot(None),
            )
            .group_by(Business.industry)
            .order_by(func.sum(Business.revenue_potential).desc())
            .limit(10)
        )
        by_industry_rows = (await session.execute(by_industry_stmt)).all()

        def _r(val: Any) -> Optional[float]:
            return round(float(val), 2) if val is not None else None

        return {
            "total_estimated": _r(agg_row.total),
            "avg_estimated": _r(agg_row.avg),
            "max_estimated": _r(agg_row.max),
            "businesses_with_estimate": agg_row.count_with,
            "by_industry": [
                {
                    "industry": r.industry,
                    "total_revenue_potential": _r(r.total),
                    "count": r.count,
                }
                for r in by_industry_rows
            ],
        }

    # ------------------------------------------------------------------
    # get_score_distribution
    # ------------------------------------------------------------------

    @staticmethod
    async def get_score_distribution(
        session: AsyncSession,
        bucket_size: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Return a frequency histogram of ``overall_score`` bucketed by
        *bucket_size* (default 10-point bands: 0–9, 10–19, …, 90–100).

        Parameters
        ----------
        bucket_size:
            Width of each score band (default 10).  Valid values: 5, 10, 20, 25.

        Returns
        -------
        list[dict]
            Each dict: ``{range_label, min, max, count}``
            sorted by ``min`` ascending.
        """
        if bucket_size not in (5, 10, 20, 25):
            bucket_size = 10

        stmt = (
            select(Business.overall_score)
            .where(Business.overall_score.isnot(None))
        )
        result = await session.execute(stmt)
        scores = [row[0] for row in result.all()]

        # Build buckets
        buckets: dict[int, int] = {}
        num_buckets = 100 // bucket_size + 1
        for i in range(num_buckets):
            buckets[i * bucket_size] = 0

        for score in scores:
            bucket_key = min(int(score // bucket_size) * bucket_size, 100 - bucket_size)
            buckets[bucket_key] = buckets.get(bucket_key, 0) + 1

        distribution: list[dict[str, Any]] = []
        for min_val in sorted(buckets.keys()):
            max_val = min(min_val + bucket_size - 1, 100)
            distribution.append(
                {
                    "range_label": f"{min_val}–{max_val}",
                    "min": min_val,
                    "max": max_val,
                    "count": buckets[min_val],
                }
            )

        return distribution
