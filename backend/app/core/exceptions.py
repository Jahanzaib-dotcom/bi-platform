"""
Domain exception hierarchy and FastAPI exception handlers.

All domain errors inherit from ``BIPlatformError`` so callers can catch the
whole family with a single except clause.  Each subclass maps to a specific
HTTP status code via ``register_exception_handlers``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class BIPlatformError(Exception):
    """Root exception for all BI Platform domain errors."""

    #: Default HTTP status code returned when this error propagates to the API.
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    #: Machine-readable error code sent in the response body.
    error_code: str = "internal_error"

    def __init__(
        self,
        message: str = "An internal error occurred.",
        detail: Optional[Any] = None,
        *,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code

    def to_dict(self) -> dict:
        payload: dict = {
            "error": self.error_code,
            "message": self.message,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload


# ---------------------------------------------------------------------------
# 400 – Bad Request / Validation
# ---------------------------------------------------------------------------


class ValidationError(BIPlatformError):
    """Raised when input data fails domain-level validation."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "validation_error"

    def __init__(self, message: str = "Validation error.", detail: Any = None) -> None:
        super().__init__(message, detail)


# ---------------------------------------------------------------------------
# 401 – Authentication
# ---------------------------------------------------------------------------


class AuthenticationError(BIPlatformError):
    """Raised when a request cannot be authenticated."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "authentication_error"

    def __init__(self, message: str = "Authentication failed.", detail: Any = None) -> None:
        super().__init__(message, detail)


# ---------------------------------------------------------------------------
# 403 – Authorisation
# ---------------------------------------------------------------------------


class AuthorisationError(BIPlatformError):
    """Raised when an authenticated user lacks permission for an action."""

    status_code = status.HTTP_403_FORBIDDEN
    error_code = "authorisation_error"

    def __init__(self, message: str = "Permission denied.", detail: Any = None) -> None:
        super().__init__(message, detail)


# ---------------------------------------------------------------------------
# 404 – Not Found
# ---------------------------------------------------------------------------


class NotFoundError(BIPlatformError):
    """Generic not-found error."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"

    def __init__(self, message: str = "Resource not found.", detail: Any = None) -> None:
        super().__init__(message, detail)


class BusinessNotFoundError(NotFoundError):
    """Raised when a Business record cannot be located."""

    error_code = "business_not_found"

    def __init__(
        self,
        business_id: Optional[str | int] = None,
        message: Optional[str] = None,
    ) -> None:
        if message is None:
            if business_id is not None:
                message = f"Business '{business_id}' was not found."
            else:
                message = "Business not found."
        super().__init__(message, detail={"business_id": str(business_id)} if business_id else None)


# ---------------------------------------------------------------------------
# 409 – Conflict
# ---------------------------------------------------------------------------


class ConflictError(BIPlatformError):
    """Raised when an operation conflicts with existing state."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"

    def __init__(self, message: str = "Resource conflict.", detail: Any = None) -> None:
        super().__init__(message, detail)


# ---------------------------------------------------------------------------
# 422 – Processing / Domain errors
# ---------------------------------------------------------------------------


class AuditFailedError(BIPlatformError):
    """Raised when a business audit job fails or produces invalid results."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "audit_failed"

    def __init__(
        self,
        message: str = "Business audit failed.",
        detail: Any = None,
        *,
        business_id: Optional[str | int] = None,
        reason: Optional[str] = None,
    ) -> None:
        merged_detail: dict = {}
        if isinstance(detail, dict):
            merged_detail.update(detail)
        elif detail is not None:
            merged_detail["extra"] = detail
        if business_id is not None:
            merged_detail["business_id"] = str(business_id)
        if reason is not None:
            merged_detail["reason"] = reason
        super().__init__(message, merged_detail or None)


class DiscoveryError(BIPlatformError):
    """Raised when the discovery engine fails to find or fetch business data."""

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    error_code = "discovery_error"

    def __init__(
        self,
        message: str = "Business discovery failed.",
        detail: Any = None,
        *,
        query: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        merged_detail: dict = {}
        if isinstance(detail, dict):
            merged_detail.update(detail)
        elif detail is not None:
            merged_detail["extra"] = detail
        if query is not None:
            merged_detail["query"] = query
        if source is not None:
            merged_detail["source"] = source
        super().__init__(message, merged_detail or None)


# ---------------------------------------------------------------------------
# 429 – Rate Limiting
# ---------------------------------------------------------------------------


class RateLimitError(BIPlatformError):
    """Raised when a client exceeds the allowed request rate."""

    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"

    def __init__(
        self,
        message: str = "Rate limit exceeded. Please slow down.",
        detail: Any = None,
        *,
        retry_after: Optional[int] = None,
    ) -> None:
        merged_detail: dict = {}
        if isinstance(detail, dict):
            merged_detail.update(detail)
        elif detail is not None:
            merged_detail["extra"] = detail
        if retry_after is not None:
            merged_detail["retry_after_seconds"] = retry_after
        self._retry_after = retry_after
        super().__init__(message, merged_detail or None)


# ---------------------------------------------------------------------------
# 503 – External service errors
# ---------------------------------------------------------------------------


class ExternalServiceError(BIPlatformError):
    """Raised when a third-party service (e.g. Anthropic, SerpAPI) fails."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "external_service_error"

    def __init__(
        self,
        message: str = "An external service is unavailable.",
        detail: Any = None,
        *,
        service: Optional[str] = None,
    ) -> None:
        merged_detail: dict = {}
        if isinstance(detail, dict):
            merged_detail.update(detail)
        elif detail is not None:
            merged_detail["extra"] = detail
        if service is not None:
            merged_detail["service"] = service
        super().__init__(message, merged_detail or None)


# ---------------------------------------------------------------------------
# Exception handler registration
# ---------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """
    Attach all domain exception handlers to *app*.

    Should be called once during application startup, typically inside
    ``create_app()`` in ``main.py``.

    Usage::

        from app.core.exceptions import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
    """
    from fastapi.exceptions import RequestValidationError  # noqa: PLC0415
    from fastapi.exception_handlers import (  # noqa: PLC0415
        http_exception_handler,
        request_validation_exception_handler,
    )
    from starlette.exceptions import HTTPException as StarletteHTTPException  # noqa: PLC0415

    # Re-export structlog logger lazily to avoid circular import at module load.
    try:
        from app.core.logging import get_logger as _get_logger  # noqa: PLC0415
        _logger = _get_logger("exceptions")
    except Exception:  # pragma: no cover
        import logging
        _logger = logging.getLogger("exceptions")  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Domain errors
    # ------------------------------------------------------------------

    @app.exception_handler(BIPlatformError)
    async def bi_platform_error_handler(
        request: Request, exc: BIPlatformError
    ) -> JSONResponse:
        _logger.warning(
            "domain_error",
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            path=request.url.path,
        )
        extra_headers: dict = {}
        if isinstance(exc, RateLimitError) and exc._retry_after:
            extra_headers["Retry-After"] = str(exc._retry_after)
        if isinstance(exc, AuthenticationError):
            extra_headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_dict(),
            headers=extra_headers or None,
        )

    # ------------------------------------------------------------------
    # FastAPI / Starlette built-ins — keep original behaviour but log
    # ------------------------------------------------------------------

    @app.exception_handler(StarletteHTTPException)
    async def http_exc_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code >= 500:
            _logger.error(
                "http_error",
                status_code=exc.status_code,
                detail=exc.detail,
                path=request.url.path,
            )
        elif exc.status_code >= 400:
            _logger.warning(
                "http_error",
                status_code=exc.status_code,
                detail=exc.detail,
                path=request.url.path,
            )
        return await http_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_exc_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        _logger.info(
            "request_validation_error",
            errors=exc.errors(),
            path=request.url.path,
        )
        return await request_validation_exception_handler(request, exc)

    # ------------------------------------------------------------------
    # Catch-all for unexpected errors
    # ------------------------------------------------------------------

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        _logger.exception(
            "unhandled_exception",
            error=str(exc),
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "message": "An unexpected error occurred. Please try again later.",
            },
        )
