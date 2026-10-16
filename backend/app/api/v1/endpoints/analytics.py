"""
Analytics endpoints.

Routes
------
GET /analytics/dashboard            – main KPIs
GET /analytics/industries           – breakdown by industry
GET /analytics/geography            – breakdown by country / state / city
GET /analytics/opportunities        – opportunity-type breakdown
GET /analytics/trends               – time-series data
GET /analytics/revenue              – revenue potential estimates by industry
GET /analytics/scores-distribution  – histogram of opportunity scores
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import oauth2_scheme, verify_token
from app.models.audit import AuditReport, AuditStatus
from app.models.business import Business
from app.models.discovery_job import DiscoveryJob
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db),
) -> User:
    err = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        token_data = verify_token(token, expected_type="access")
    except Exception:
        raise err
    result = await db.execute(select(User).where(User.id == uuid.UUID(token_data.sub)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise err
    return user

# ---------------------------------------------------------------------------
# GET /analytics/dashboard
# ---------------------------------------------------------------------------


@router.get("/dashboard", status_code=200)
@router.get("/overview", status_code=200)
async def dashboard_kpis(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Return top-level KPI metrics:
    - total_businesses
    - total_audited      (business has at least one completed audit)
    - total_without_website
    - avg_overall_score
    - avg_opportunity_score
    - total_discovery_jobs
    - businesses_last_30_days
    """
    # Total businesses
    total_biz = (await db.execute(select(func.count(Business.id)))).scalar_one()

    # Total without website
    no_website = (
        await db.execute(
            select(func.count(Business.id)).where(Business.has_website == False)
        )
    ).scalar_one()

    # Total audited (audit_count > 0)
    audited = (
        await db.execute(
            select(func.count(Business.id)).where(Business.audit_count > 0)
        )
    ).scalar_one()

    # Average scores
    avg_row = await db.execute(
        select(
            func.avg(Business.overall_score).label("avg_overall"),
            func.avg(Business.opportunity_score).label("avg_opportunity"),
            func.avg(Business.revenue_potential).label("avg_revenue"),
        )
    )
    avg_data = avg_row.mappings().one()

    # Total discovery jobs
    total_jobs = (
        await db.execute(select(func.count(DiscoveryJob.id)))
    ).scalar_one()

    # New businesses in the last 30 days
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    new_30d = (
        await db.execute(
            select(func.count(Business.id)).where(Business.created_at >= cutoff)
        )
    ).scalar_one()

    # Total completed audits
    total_audits_completed = (
        await db.execute(
            select(func.count(AuditReport.id)).where(
                AuditReport.status == AuditStatus.completed
            )
        )
    ).scalar_one()

    return {
        "total_businesses": total_biz,
        "total_audited": audited,
        "total_without_website": no_website,
        "total_with_website": total_biz - no_website,
        "avg_overall_score": (
            round(float(avg_data["avg_overall"]), 1)
            if avg_data["avg_overall"] is not None
            else None
        ),
        "avg_opportunity_score": (
            round(float(avg_data["avg_opportunity"]), 1)
            if avg_data["avg_opportunity"] is not None
            else None
        ),
        "avg_revenue_potential": (
            round(float(avg_data["avg_revenue"]), 2)
            if avg_data["avg_revenue"] is not None
            else None
        ),
        "total_discovery_jobs": total_jobs,
        "total_audits_completed": total_audits_completed,
        "businesses_added_last_30_days": new_30d,
    }


# ---------------------------------------------------------------------------
# GET /analytics/industries
# ---------------------------------------------------------------------------


@router.get("/industries", status_code=200)
async def industries_breakdown(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return business counts and average scores grouped by industry."""
    stmt = (
        select(
            Business.industry,
            func.count(Business.id).label("count"),
            func.avg(Business.overall_score).label("avg_score"),
            func.avg(Business.opportunity_score).label("avg_opportunity_score"),
            func.sum(
                case((Business.has_website == True, 1), else_=0)
            ).label("with_website"),
            func.sum(
                case((Business.has_website == False, 1), else_=0)
            ).label("without_website"),
        )
        .where(Business.industry.isnot(None))
        .group_by(Business.industry)
        .order_by(func.count(Business.id).desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)
    items = []
    for row in rows.mappings():
        items.append(
            {
                "industry": row["industry"],
                "count": row["count"],
                "avg_score": (
                    round(float(row["avg_score"]), 1)
                    if row["avg_score"] is not None
                    else None
                ),
                "avg_opportunity_score": (
                    round(float(row["avg_opportunity_score"]), 1)
                    if row["avg_opportunity_score"] is not None
                    else None
                ),
                "with_website": row["with_website"] or 0,
                "without_website": row["without_website"] or 0,
            }
        )

    return {"items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# GET /analytics/geography
# ---------------------------------------------------------------------------


@router.get("/geography", status_code=200)
async def geography_breakdown(
    group_by: str = Query("country", pattern="^(country|state|city)$"),
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """Return business counts grouped by country, state, or city."""
    col_map = {
        "country": Business.country,
        "state": Business.state,
        "city": Business.city,
    }
    group_col = col_map[group_by]

    stmt = (
        select(
            group_col.label("location"),
            func.count(Business.id).label("count"),
            func.avg(Business.overall_score).label("avg_score"),
            func.sum(
                case((Business.has_website == True, 1), else_=0)
            ).label("with_website"),
        )
        .where(group_col.isnot(None))
        .group_by(group_col)
        .order_by(func.count(Business.id).desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)
    items = [
        {
            "location": row["location"],
            "count": row["count"],
            "avg_score": (
                round(float(row["avg_score"]), 1)
                if row["avg_score"] is not None
                else None
            ),
            "with_website": row["with_website"] or 0,
        }
        for row in rows.mappings()
    ]

    return {"group_by": group_by, "items": items, "total": len(items)}


# ---------------------------------------------------------------------------
# GET /analytics/opportunities
# ---------------------------------------------------------------------------


@router.get("/opportunities", status_code=200)
async def opportunity_breakdown(
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Break businesses into opportunity tiers based on website presence and
    opportunity score:

    - no_website       : has_website=False
    - low_score        : has_website=True, overall_score < 40
    - medium_score     : has_website=True, 40 <= overall_score < 70
    - high_score       : has_website=True, overall_score >= 70
    - not_yet_audited  : has_website=True, overall_score IS NULL
    """
    total_stmt = select(func.count(Business.id))
    total = (await db.execute(total_stmt)).scalar_one()

    no_website = (
        await db.execute(
            select(func.count(Business.id)).where(Business.has_website == False)
        )
    ).scalar_one()

    low_score = (
        await db.execute(
            select(func.count(Business.id)).where(
                Business.has_website == True,
                Business.overall_score.isnot(None),
                Business.overall_score < 40,
            )
        )
    ).scalar_one()

    medium_score = (
        await db.execute(
            select(func.count(Business.id)).where(
                Business.has_website == True,
                Business.overall_score.isnot(None),
                Business.overall_score >= 40,
                Business.overall_score < 70,
            )
        )
    ).scalar_one()

    high_score = (
        await db.execute(
            select(func.count(Business.id)).where(
                Business.has_website == True,
                Business.overall_score.isnot(None),
                Business.overall_score >= 70,
            )
        )
    ).scalar_one()

    not_audited = (
        await db.execute(
            select(func.count(Business.id)).where(
                Business.has_website == True,
                Business.overall_score.is_(None),
            )
        )
    ).scalar_one()

    def pct(n: int) -> Optional[float]:
        return round(n / total * 100, 1) if total else None

    return {
        "total": total,
        "breakdown": [
            {
                "type": "no_website",
                "label": "No Website",
                "count": no_website,
                "percentage": pct(no_website),
            },
            {
                "type": "not_yet_audited",
                "label": "Not Yet Audited",
                "count": not_audited,
                "percentage": pct(not_audited),
            },
            {
                "type": "low_score",
                "label": "Low Score (< 40)",
                "count": low_score,
                "percentage": pct(low_score),
            },
            {
                "type": "medium_score",
                "label": "Medium Score (40–69)",
                "count": medium_score,
                "percentage": pct(medium_score),
            },
            {
                "type": "high_score",
                "label": "High Score (≥ 70)",
                "count": high_score,
                "percentage": pct(high_score),
            },
        ],
    }


# ---------------------------------------------------------------------------
# GET /analytics/trends
# ---------------------------------------------------------------------------


@router.get("/trends", status_code=200)
async def trends(
    days: int = Query(30, ge=7, le=365, description="Number of days to look back"),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Return daily counts of new businesses discovered and audits completed
    over the last *days* days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Daily new businesses
    biz_stmt = (
        select(
            func.date(Business.created_at).label("day"),
            func.count(Business.id).label("count"),
        )
        .where(Business.created_at >= cutoff)
        .group_by(func.date(Business.created_at))
        .order_by(func.date(Business.created_at))
    )
    biz_rows = await db.execute(biz_stmt)
    biz_series = [
        {"date": str(r.day), "count": r.count} for r in biz_rows
    ]

    # Daily completed audits
    audit_stmt = (
        select(
            func.date(AuditReport.completed_at).label("day"),
            func.count(AuditReport.id).label("count"),
        )
        .where(
            AuditReport.status == AuditStatus.completed,
            AuditReport.completed_at >= cutoff,
        )
        .group_by(func.date(AuditReport.completed_at))
        .order_by(func.date(AuditReport.completed_at))
    )
    audit_rows = await db.execute(audit_stmt)
    audit_series = [
        {"date": str(r.day), "count": r.count} for r in audit_rows
    ]

    return {
        "period_days": days,
        "businesses_discovered": biz_series,
        "audits_completed": audit_series,
    }


# ---------------------------------------------------------------------------
# GET /analytics/revenue
# ---------------------------------------------------------------------------


@router.get("/revenue", status_code=200)
async def revenue_estimates(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Return total and average revenue potential estimates grouped by industry.
    Only businesses with a non-null *revenue_potential* are included.
    """
    stmt = (
        select(
            Business.industry,
            func.count(Business.id).label("count"),
            func.sum(Business.revenue_potential).label("total_revenue"),
            func.avg(Business.revenue_potential).label("avg_revenue"),
            func.min(Business.revenue_potential).label("min_revenue"),
            func.max(Business.revenue_potential).label("max_revenue"),
        )
        .where(
            Business.industry.isnot(None),
            Business.revenue_potential.isnot(None),
        )
        .group_by(Business.industry)
        .order_by(func.sum(Business.revenue_potential).desc())
        .limit(limit)
    )
    rows = await db.execute(stmt)
    items = [
        {
            "industry": row["industry"],
            "count": row["count"],
            "total_revenue_potential": (
                round(float(row["total_revenue"]), 2)
                if row["total_revenue"] is not None
                else None
            ),
            "avg_revenue_potential": (
                round(float(row["avg_revenue"]), 2)
                if row["avg_revenue"] is not None
                else None
            ),
            "min_revenue_potential": (
                round(float(row["min_revenue"]), 2)
                if row["min_revenue"] is not None
                else None
            ),
            "max_revenue_potential": (
                round(float(row["max_revenue"]), 2)
                if row["max_revenue"] is not None
                else None
            ),
        }
        for row in rows.mappings()
    ]

    grand_total = sum(
        (i["total_revenue_potential"] or 0) for i in items
    )

    return {
        "items": items,
        "total": len(items),
        "grand_total_revenue_potential": round(grand_total, 2),
    }


# ---------------------------------------------------------------------------
# GET /analytics/scores-distribution
# ---------------------------------------------------------------------------


@router.get("/scores-distribution", status_code=200)
async def scores_distribution(
    buckets: int = Query(10, ge=5, le=20, description="Number of histogram buckets"),
    score_field: str = Query(
        "overall_score",
        pattern="^(overall_score|opportunity_score|priority_score)$",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: Any = Depends(_get_current_user),
) -> Dict[str, Any]:
    """
    Return a histogram of opportunity/overall scores across all businesses.
    Scores are bucketed into equal-width bands across the 0–100 range.
    """
    col_map = {
        "overall_score": Business.overall_score,
        "opportunity_score": Business.opportunity_score,
        "priority_score": Business.priority_score,
    }
    score_col = col_map[score_field]

    bucket_width = 100.0 / buckets

    # Build histogram buckets in Python after fetching all non-null scores
    stmt = select(score_col).where(score_col.isnot(None))
    rows = await db.execute(stmt)
    scores = [float(r[0]) for r in rows if r[0] is not None]

    histogram: List[Dict[str, Any]] = []
    for i in range(buckets):
        low = i * bucket_width
        high = low + bucket_width
        label = f"{low:.0f}–{high:.0f}"
        count = sum(1 for s in scores if low <= s < high)
        histogram.append(
            {
                "bucket": i,
                "label": label,
                "range_low": low,
                "range_high": high,
                "count": count,
            }
        )

    # Edge-case: score == 100 falls into the last bucket
    if scores:
        histogram[-1]["count"] += sum(1 for s in scores if s == 100.0)

    return {
        "score_field": score_field,
        "total_with_score": len(scores),
        "buckets": buckets,
        "histogram": histogram,
    }
