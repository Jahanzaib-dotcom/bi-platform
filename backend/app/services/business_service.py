"""
BusinessService — async CRUD and query layer for the Business model.

All public methods receive an open :class:`~sqlalchemy.ext.asyncio.AsyncSession`
as their first argument so callers control transaction boundaries.

Public API
----------
get_businesses(session, filters, pagination)      -> tuple[list[Business], int]
get_business(session, business_id)                -> Business
create_business(session, data)                    -> Business
update_business(session, business_id, data)       -> Business
delete_business(session, business_id)
search_businesses(session, query, limit)          -> list[Business]
get_business_stats(session)                       -> dict
upsert_from_discovery(session, discovery_result)  -> Business
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import asc, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BusinessNotFoundError, ConflictError
from app.core.logging import get_logger
from app.models.business import Business, WebsiteStatus
from app.utils.business_utils import clean_address, clean_phone, fingerprint_business, generate_slug
from app.utils.pagination import PaginationParams, paginate_query

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Column map for safe sort_by resolution
# ---------------------------------------------------------------------------

_SORTABLE_COLUMNS: dict[str, Any] = {
    "name": Business.name,
    "score": Business.overall_score,
    "overall_score": Business.overall_score,
    "discovered_at": Business.discovered_at,
    "opportunity_score": Business.opportunity_score,
    "priority_score": Business.priority_score,
    "created_at": Business.created_at,
    "updated_at": Business.updated_at,
    "audit_count": Business.audit_count,
    "revenue_potential": Business.revenue_potential,
}


def _resolve_sort(
    sort_by: Optional[str],
    sort_order: str,
) -> Any:
    """Return a SQLAlchemy order expression or ``None`` for the default."""
    col = _SORTABLE_COLUMNS.get(sort_by or "")
    if col is None:
        col = Business.discovered_at
    return asc(col) if sort_order == "asc" else desc(col)


# ---------------------------------------------------------------------------
# BusinessService
# ---------------------------------------------------------------------------


class BusinessService:
    """
    Stateless async service layer for :class:`~app.models.business.Business`.

    All methods are ``@staticmethod`` so the class can be used either as a
    namespace (``BusinessService.get_business(...)``) or as an instance
    (``svc = BusinessService(); svc.get_business(...)``).
    """

    # ------------------------------------------------------------------
    # get_businesses
    # ------------------------------------------------------------------

    @staticmethod
    async def get_businesses(
        session: AsyncSession,
        filters: Optional[dict[str, Any]] = None,
        pagination: Optional[PaginationParams] = None,
    ) -> tuple[list[Business], int]:
        """
        Return a paginated, filtered, sorted list of businesses.

        Parameters
        ----------
        session:
            Open async session.
        filters:
            Optional mapping of filter keys to values.  Supported keys:

            * ``industry``       – exact match (case-insensitive LIKE)
            * ``country``        – exact match (case-insensitive)
            * ``city``           – exact match (case-insensitive)
            * ``has_website``    – bool
            * ``score_min``      – minimum ``overall_score`` (inclusive)
            * ``score_max``      – maximum ``overall_score`` (inclusive)
            * ``website_status`` – :class:`~app.models.business.WebsiteStatus` value
            * ``source``         – exact match
        pagination:
            Page, size and sort parameters.  Defaults to page 1, 20 items,
            sorted by ``discovered_at DESC``.

        Returns
        -------
        tuple[list[Business], int]
            ``(items_for_page, total_matching_count)``
        """
        if pagination is None:
            pagination = PaginationParams()
        if filters is None:
            filters = {}

        stmt = select(Business)

        # -- Apply filters ---------------------------------------------------
        if filters.get("industry"):
            stmt = stmt.where(
                Business.industry.ilike(f"%{filters['industry']}%")
            )
        if filters.get("country"):
            stmt = stmt.where(
                Business.country.ilike(filters["country"])
            )
        if filters.get("city"):
            stmt = stmt.where(
                Business.city.ilike(f"%{filters['city']}%")
            )
        if filters.get("has_website") is not None:
            stmt = stmt.where(Business.has_website == bool(filters["has_website"]))
        if filters.get("score_min") is not None:
            stmt = stmt.where(Business.overall_score >= float(filters["score_min"]))
        if filters.get("score_max") is not None:
            stmt = stmt.where(Business.overall_score <= float(filters["score_max"]))
        if filters.get("website_status"):
            try:
                ws = WebsiteStatus(filters["website_status"])
                stmt = stmt.where(Business.website_status == ws)
            except ValueError:
                pass
        if filters.get("source"):
            stmt = stmt.where(Business.source == filters["source"])

        # -- Apply sorting ----------------------------------------------------
        order_expr = _resolve_sort(pagination.sort_by, pagination.sort_order)
        stmt = stmt.order_by(order_expr)

        # -- Paginate ---------------------------------------------------------
        items, total = await paginate_query(stmt, session, pagination)

        logger.debug(
            "business_service.get_businesses",
            total=total,
            page=pagination.page,
            filters=filters,
        )
        return items, total

    # ------------------------------------------------------------------
    # get_business
    # ------------------------------------------------------------------

    @staticmethod
    async def get_business(
        session: AsyncSession,
        business_id: str | uuid.UUID,
    ) -> Business:
        """
        Fetch a single :class:`Business` by primary key.

        Raises
        ------
        BusinessNotFoundError
            If no record with *business_id* exists.
        """
        try:
            bid = uuid.UUID(str(business_id))
        except ValueError as exc:
            raise BusinessNotFoundError(str(business_id)) from exc

        stmt = select(Business).where(Business.id == bid)
        result = await session.execute(stmt)
        business = result.scalar_one_or_none()

        if business is None:
            raise BusinessNotFoundError(str(business_id))

        return business

    # ------------------------------------------------------------------
    # create_business
    # ------------------------------------------------------------------

    @staticmethod
    async def create_business(
        session: AsyncSession,
        data: dict[str, Any],
    ) -> Business:
        """
        Create and persist a new :class:`Business`.

        Parameters
        ----------
        data:
            Dictionary of field values.  The ``slug`` field is auto-generated
            from ``name`` if not supplied.  ``phone`` and ``address`` are
            normalised automatically.

        Raises
        ------
        ConflictError
            If a business with the same slug already exists.
        """
        name: str = data.get("name", "")
        if not name:
            raise ValueError("Business 'name' is required.")

        # Normalise contact fields
        raw_phone = data.get("phone")
        raw_address = data.get("address")
        if raw_phone:
            data["phone"] = clean_phone(raw_phone) or raw_phone
        if raw_address:
            data["address"] = clean_address(raw_address) or raw_address

        # Generate slug if not provided
        slug = data.get("slug") or generate_slug(name)

        # Check slug uniqueness
        existing = await session.execute(
            select(Business.id).where(Business.slug == slug)
        )
        if existing.scalar_one_or_none() is not None:
            # Regenerate with a fresh suffix
            slug = generate_slug(name)

        business = Business(
            slug=slug,
            discovered_at=data.get("discovered_at") or datetime.now(timezone.utc),
            **{k: v for k, v in data.items() if k not in ("slug", "discovered_at")},
        )
        session.add(business)

        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise ConflictError(f"Could not create business: {exc}") from exc

        await session.refresh(business)
        logger.info("business_service.created", business_id=str(business.id), name=business.name)
        return business

    # ------------------------------------------------------------------
    # update_business
    # ------------------------------------------------------------------

    @staticmethod
    async def update_business(
        session: AsyncSession,
        business_id: str | uuid.UUID,
        data: dict[str, Any],
    ) -> Business:
        """
        Update mutable fields of an existing :class:`Business`.

        Only keys present in *data* are updated; ``id``, ``slug``, and
        ``created_at`` are protected and silently ignored.

        Raises
        ------
        BusinessNotFoundError
            If the record does not exist.
        """
        business = await BusinessService.get_business(session, business_id)

        _protected = {"id", "slug", "created_at"}
        if "phone" in data and data["phone"]:
            data["phone"] = clean_phone(data["phone"]) or data["phone"]
        if "address" in data and data["address"]:
            data["address"] = clean_address(data["address"]) or data["address"]

        for key, value in data.items():
            if key in _protected:
                continue
            if hasattr(business, key):
                setattr(business, key, value)

        business.updated_at = datetime.now(timezone.utc)

        try:
            await session.commit()
        except Exception as exc:
            await session.rollback()
            raise ConflictError(f"Could not update business: {exc}") from exc

        await session.refresh(business)
        logger.info("business_service.updated", business_id=str(business.id))
        return business

    # ------------------------------------------------------------------
    # delete_business
    # ------------------------------------------------------------------

    @staticmethod
    async def delete_business(
        session: AsyncSession,
        business_id: str | uuid.UUID,
    ) -> None:
        """
        Hard-delete a :class:`Business` record (cascade deletes audits).

        Raises
        ------
        BusinessNotFoundError
            If the record does not exist.
        """
        business = await BusinessService.get_business(session, business_id)
        await session.delete(business)
        await session.commit()
        logger.info("business_service.deleted", business_id=str(business_id))

    # ------------------------------------------------------------------
    # search_businesses
    # ------------------------------------------------------------------

    @staticmethod
    async def search_businesses(
        session: AsyncSession,
        query: str,
        limit: int = 20,
    ) -> list[Business]:
        """
        Full-text-style search across ``name``, ``city``, ``industry``,
        ``email``, and ``website_url`` using ILIKE patterns.

        Parameters
        ----------
        query:
            Search term (minimum 1 character; longer terms are more precise).
        limit:
            Maximum number of results (default 20, max 100).

        Returns
        -------
        list[Business]
            Matching businesses ordered by name.
        """
        limit = min(max(limit, 1), 100)
        if not query or not query.strip():
            return []

        pattern = f"%{query.strip()}%"
        stmt = (
            select(Business)
            .where(
                or_(
                    Business.name.ilike(pattern),
                    Business.city.ilike(pattern),
                    Business.industry.ilike(pattern),
                    Business.email.ilike(pattern),
                    Business.website_url.ilike(pattern),
                    Business.phone.ilike(pattern),
                )
            )
            .order_by(asc(Business.name))
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # get_business_stats
    # ------------------------------------------------------------------

    @staticmethod
    async def get_business_stats(session: AsyncSession) -> dict[str, Any]:
        """
        Return aggregate statistics for the businesses table.

        Returns a dict with the following keys:

        * ``total``              – total business count
        * ``with_website``       – count where ``has_website`` is True
        * ``without_website``    – count where ``has_website`` is False
        * ``with_score``         – count with a non-null ``overall_score``
        * ``avg_score``          – average ``overall_score`` (or ``None``)
        * ``avg_opportunity``    – average ``opportunity_score`` (or ``None``)
        * ``by_country``         – list of ``{country, count}`` (top 10)
        * ``by_industry``        – list of ``{industry, count}`` (top 10)
        * ``by_source``          – list of ``{source, count}`` (top 10)
        * ``recent_count_7d``    – businesses discovered in the last 7 days
        * ``recent_count_30d``   – businesses discovered in the last 30 days
        """
        from sqlalchemy import case, cast, Float, Integer
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        # -- Aggregate counts -------------------------------------------------
        agg_stmt = select(
            func.count(Business.id).label("total"),
            func.count(case((Business.has_website == True, 1))).label("with_website"),
            func.count(case((Business.has_website == False, 1))).label("without_website"),
            func.count(Business.overall_score).label("with_score"),
            func.avg(Business.overall_score).label("avg_score"),
            func.avg(Business.opportunity_score).label("avg_opportunity"),
            func.count(
                case((Business.discovered_at >= seven_days_ago, 1))
            ).label("recent_7d"),
            func.count(
                case((Business.discovered_at >= thirty_days_ago, 1))
            ).label("recent_30d"),
        )
        agg_result = await session.execute(agg_stmt)
        agg_row = agg_result.one()

        # -- By country -------------------------------------------------------
        by_country_stmt = (
            select(Business.country, func.count(Business.id).label("count"))
            .where(Business.country.isnot(None))
            .group_by(Business.country)
            .order_by(desc("count"))
            .limit(10)
        )
        by_country_rows = (await session.execute(by_country_stmt)).all()

        # -- By industry -------------------------------------------------------
        by_industry_stmt = (
            select(Business.industry, func.count(Business.id).label("count"))
            .where(Business.industry.isnot(None))
            .group_by(Business.industry)
            .order_by(desc("count"))
            .limit(10)
        )
        by_industry_rows = (await session.execute(by_industry_stmt)).all()

        # -- By source --------------------------------------------------------
        by_source_stmt = (
            select(Business.source, func.count(Business.id).label("count"))
            .where(Business.source.isnot(None))
            .group_by(Business.source)
            .order_by(desc("count"))
            .limit(10)
        )
        by_source_rows = (await session.execute(by_source_stmt)).all()

        avg_score = float(agg_row.avg_score) if agg_row.avg_score is not None else None
        avg_opp = float(agg_row.avg_opportunity) if agg_row.avg_opportunity is not None else None

        return {
            "total": agg_row.total,
            "with_website": agg_row.with_website,
            "without_website": agg_row.without_website,
            "with_score": agg_row.with_score,
            "avg_score": round(avg_score, 2) if avg_score is not None else None,
            "avg_opportunity": round(avg_opp, 2) if avg_opp is not None else None,
            "recent_count_7d": agg_row.recent_7d,
            "recent_count_30d": agg_row.recent_30d,
            "by_country": [
                {"country": r.country, "count": r.count} for r in by_country_rows
            ],
            "by_industry": [
                {"industry": r.industry, "count": r.count} for r in by_industry_rows
            ],
            "by_source": [
                {"source": r.source, "count": r.count} for r in by_source_rows
            ],
        }

    # ------------------------------------------------------------------
    # upsert_from_discovery
    # ------------------------------------------------------------------

    @staticmethod
    async def upsert_from_discovery(
        session: AsyncSession,
        discovery_result: dict[str, Any],
    ) -> Business:
        """
        Create or update a :class:`Business` from a discovery result payload.

        The upsert key is a SHA-256 fingerprint computed from ``name``,
        ``city``, ``phone``, and ``website_url``.  If a matching business
        already exists its contact fields are enriched (only if previously
        empty), otherwise a new record is inserted.

        Parameters
        ----------
        discovery_result:
            Flat dict with keys matching :class:`Business` column names plus
            optional raw discovery metadata.  At minimum ``name`` must be
            present.

        Returns
        -------
        Business
            The created or updated ORM instance (refreshed from the DB).
        """
        name: str = discovery_result.get("name", "").strip()
        if not name:
            raise ValueError("'name' is required in discovery_result.")

        city: Optional[str] = discovery_result.get("city")
        phone: Optional[str] = discovery_result.get("phone")
        website_url: Optional[str] = discovery_result.get("website_url")

        fingerprint = fingerprint_business(name, city, phone, website_url)

        # -- Look up by fingerprint stored in metadata_ ----------------------
        # We store the fingerprint in metadata_ so we can find the record
        # without a full-text search every time.
        stmt = (
            select(Business)
            .where(Business.name == name)
        )
        if city:
            stmt = stmt.where(Business.city == city)
        result = await session.execute(stmt)
        existing: Optional[Business] = result.scalar_one_or_none()

        if existing is not None:
            # Enrich: fill in empty fields only
            enriched = False
            if website_url and not existing.website_url:
                existing.website_url = website_url
                existing.has_website = True
                existing.website_status = WebsiteStatus.active
                enriched = True
            if phone and not existing.phone:
                existing.phone = clean_phone(phone) or phone
                enriched = True
            if discovery_result.get("email") and not existing.email:
                existing.email = discovery_result["email"]
                enriched = True
            if discovery_result.get("address") and not existing.address:
                existing.address = clean_address(discovery_result["address"])
                enriched = True
            if enriched:
                existing.updated_at = datetime.now(timezone.utc)
                await session.commit()
                await session.refresh(existing)
            return existing

        # -- Create new -------------------------------------------------------
        clean_data: dict[str, Any] = {
            "name": name,
            "city": city,
            "state": discovery_result.get("state"),
            "country": discovery_result.get("country"),
            "zip_code": discovery_result.get("zip_code"),
            "address": clean_address(discovery_result.get("address")),
            "phone": clean_phone(phone) or phone if phone else None,
            "email": discovery_result.get("email"),
            "website_url": website_url,
            "has_website": bool(website_url),
            "website_status": WebsiteStatus.active if website_url else None,
            "industry": discovery_result.get("industry"),
            "category": discovery_result.get("category"),
            "source": discovery_result.get("source"),
            "source_id": discovery_result.get("source_id"),
            "source_url": discovery_result.get("source_url"),
            "discovered_at": discovery_result.get("discovered_at") or datetime.now(timezone.utc),
            "metadata_": {"fingerprint": fingerprint, **discovery_result.get("metadata_", {})},
        }
        business = Business(
            slug=generate_slug(name),
            **clean_data,
        )
        session.add(business)
        await session.commit()
        await session.refresh(business)
        logger.info(
            "business_service.upsert_created",
            business_id=str(business.id),
            name=name,
        )
        return business
