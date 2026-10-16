"""
Pagination utilities for SQLAlchemy async queries.

Classes
-------
PaginationParams
    Validated page/size/sort parameters parsed from query strings.
PaginatedResponse
    Generic paginated envelope returned by list endpoints.

Functions
---------
paginate_query(query, session, pagination) -> tuple[list, int]
    Apply LIMIT/OFFSET to a SQLAlchemy select statement and return
    (items, total_count) in a single round-trip using a window function
    or a separate COUNT query depending on DB dialect.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Generic, Optional, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 200


# ---------------------------------------------------------------------------
# PaginationParams
# ---------------------------------------------------------------------------


@dataclass
class PaginationParams:
    """
    Validated pagination / sorting parameters.

    Attributes
    ----------
    page:
        1-indexed page number (default 1).
    page_size:
        Number of items per page (default 20, max 200).
    sort_by:
        Column name to sort on (caller is responsible for validation).
    sort_order:
        ``"asc"`` or ``"desc"`` (default ``"desc"``).
    """

    page: int = DEFAULT_PAGE
    page_size: int = DEFAULT_PAGE_SIZE
    sort_by: Optional[str] = None
    sort_order: str = "desc"

    def __post_init__(self) -> None:
        if self.page < 1:
            self.page = 1
        if self.page_size < 1:
            self.page_size = 1
        if self.page_size > MAX_PAGE_SIZE:
            self.page_size = MAX_PAGE_SIZE
        if self.sort_order not in ("asc", "desc"):
            self.sort_order = "desc"

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size

    @classmethod
    def from_query(
        cls,
        page: int = DEFAULT_PAGE,
        page_size: int = DEFAULT_PAGE_SIZE,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
    ) -> "PaginationParams":
        """Convenience constructor for use with FastAPI query parameters."""
        return cls(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
        )


# ---------------------------------------------------------------------------
# PaginatedResponse
# ---------------------------------------------------------------------------


@dataclass
class PaginatedResponse(Generic[T]):
    """
    Generic paginated envelope.

    Attributes
    ----------
    items:
        The items for the current page.
    total:
        Total number of items across all pages.
    page:
        Current 1-indexed page number.
    page_size:
        Number of items per page requested.
    total_pages:
        Total number of pages (ceiling of total / page_size).
    has_next:
        Whether a next page exists.
    has_prev:
        Whether a previous page exists.
    """

    items: Sequence[T]
    total: int
    page: int
    page_size: int
    total_pages: int = field(init=False)
    has_next: bool = field(init=False)
    has_prev: bool = field(init=False)

    def __post_init__(self) -> None:
        self.total_pages = max(1, math.ceil(self.total / self.page_size)) if self.page_size else 1
        self.has_next = self.page < self.total_pages
        self.has_prev = self.page > 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": self.total_pages,
            "has_next": self.has_next,
            "has_prev": self.has_prev,
        }

    @classmethod
    def from_params(
        cls,
        items: Sequence[T],
        total: int,
        params: PaginationParams,
    ) -> "PaginatedResponse[T]":
        return cls(
            items=items,
            total=total,
            page=params.page,
            page_size=params.page_size,
        )


# ---------------------------------------------------------------------------
# paginate_query
# ---------------------------------------------------------------------------


async def paginate_query(
    query: Select,
    session: AsyncSession,
    pagination: PaginationParams,
) -> tuple[list[Any], int]:
    """
    Execute *query* with pagination applied and return ``(items, total_count)``.

    The total count is retrieved via a separate ``SELECT COUNT(*)`` sub-query
    derived from *query* (before LIMIT/OFFSET are applied). This is compatible
    with both PostgreSQL and SQLite.

    Parameters
    ----------
    query:
        A SQLAlchemy ``select(...)`` statement (no LIMIT/OFFSET applied yet).
    session:
        An open async SQLAlchemy session.
    pagination:
        Validated :class:`PaginationParams` instance.

    Returns
    -------
    tuple[list, int]
        ``(items_for_current_page, total_count)``
    """
    # -- Count query ----------------------------------------------------------
    # Wrap the original query as a sub-query and count rows.
    count_subq = query.order_by(None).subquery()
    count_stmt = select(func.count()).select_from(count_subq)
    count_result = await session.execute(count_stmt)
    total: int = count_result.scalar_one() or 0

    if total == 0:
        return [], 0

    # -- Data query -----------------------------------------------------------
    data_stmt = query.offset(pagination.offset).limit(pagination.limit)
    data_result = await session.execute(data_stmt)
    # Support both ORM-mapped rows and plain scalars
    rows = data_result.scalars().all()

    return list(rows), total
