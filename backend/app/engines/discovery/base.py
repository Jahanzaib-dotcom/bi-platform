"""Abstract base classes for discovery providers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, Optional


@dataclass
class BusinessResult:
    """Normalised business record yielded by any discovery provider."""

    name: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = None
    category: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)


class BaseDiscoveryProvider(ABC):
    """Abstract base class that every discovery provider must implement."""

    # ------------------------------------------------------------------
    # Identity / limits
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique slug for this provider (e.g. ``"duckduckgo"``)."""

    @property
    @abstractmethod
    def rate_limit(self) -> int:
        """Maximum number of HTTP requests per minute this provider allows."""

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    @abstractmethod
    async def discover(
        self,
        query: str,
        country: Optional[str] = None,
        industry: Optional[str] = None,
        city: Optional[str] = None,
        max_results: int = 100,
    ) -> AsyncGenerator[BusinessResult, None]:
        """
        Yield :class:`BusinessResult` objects matching the given criteria.

        The generator must honour *max_results* and must not raise unless
        the error is unrecoverable.  Transient network errors should be
        swallowed after retries and surfaced via the health-check instead.
        """
        # Make this an async generator signature (``yield`` in body).
        # Subclasses that override must be ``async def`` with ``yield``.
        raise NotImplementedError
        yield  # pragma: no cover – forces the type to AsyncGenerator

    @abstractmethod
    async def validate_config(self) -> bool:
        """Return ``True`` when all required credentials / dependencies are present."""

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Return a status dict, e.g.::

            {
                "provider": "duckduckgo",
                "healthy": True,
                "latency_ms": 142,
                "message": "OK",
            }
        """
