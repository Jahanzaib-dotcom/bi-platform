from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BaseModel(Base):
    """Abstract base that every domain model inherits from."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation of this model instance."""
        # Build a mapping from DB column name → Python attribute name to handle
        # columns with an explicit key different from the attribute (e.g. metadata_ → "metadata").
        col_to_attr: dict[str, str] = {}
        for mapper_prop in self.__mapper__.column_attrs:
            for col in mapper_prop.columns:
                col_to_attr[col.key] = mapper_prop.key

        result: dict[str, Any] = {}
        for column in self.__table__.columns:
            attr_name = col_to_attr.get(column.key, column.key)
            value = getattr(self, attr_name, None)
            if isinstance(value, uuid.UUID):
                value = str(value)
            elif isinstance(value, datetime):
                value = value.isoformat()
            result[column.key] = value
        return result
