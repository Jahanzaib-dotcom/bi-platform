"""
Structured logging configuration using structlog.

- JSON output in production / staging
- Human-readable coloured output in development
- Request-ID propagation via context vars
- get_logger(name) factory for consistent usage across the codebase
"""
from __future__ import annotations

import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any, Callable

import structlog
from structlog.types import EventDict, WrappedLogger

# ---------------------------------------------------------------------------
# Context variable for request-scoped correlation ID
# ---------------------------------------------------------------------------

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request ID (empty string outside a request context)."""
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    """Set the current request ID in the context variable."""
    _request_id_ctx.set(request_id)


# ---------------------------------------------------------------------------
# Custom structlog processors
# ---------------------------------------------------------------------------


def _add_request_id(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Inject the current request ID into every log record."""
    rid = get_request_id()
    if rid:
        event_dict["request_id"] = rid
    return event_dict


def _add_app_info(
    logger: WrappedLogger, method: str, event_dict: EventDict
) -> EventDict:
    """Inject static application metadata once on setup."""
    # Avoid circular import; read lazily.
    try:
        from app.core.config import settings  # noqa: PLC0415

        event_dict.setdefault("app", settings.APP_NAME)
        event_dict.setdefault("env", settings.APP_ENV)
    except Exception:  # pragma: no cover
        pass
    return event_dict


# ---------------------------------------------------------------------------
# Setup function
# ---------------------------------------------------------------------------


def setup_logging(log_level: str = "INFO", json_logs: bool | None = None) -> None:
    """
    Configure structlog and the standard-library root logger.

    Parameters
    ----------
    log_level:
        Root log level string, e.g. ``"DEBUG"``, ``"INFO"``.
    json_logs:
        When *None* (default) JSON is used unless ``APP_ENV == "development"``.
        Pass an explicit ``True`` / ``False`` to override.
    """
    try:
        from app.core.config import settings  # noqa: PLC0415

        if json_logs is None:
            json_logs = not settings.is_development
    except Exception:
        json_logs = json_logs if json_logs is not None else False

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # --- Shared processors that run regardless of renderer ---
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_request_id,
        _add_app_info,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        # Production: newline-delimited JSON
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        # Development: pretty coloured output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(numeric_level)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Return a structlog bound logger for *name*.

    Usage::

        logger = get_logger(__name__)
        logger.info("event happened", key="value")
    """
    return structlog.get_logger(name)


# ---------------------------------------------------------------------------
# ASGI / Starlette middleware
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware:
    """
    ASGI middleware that:
    - Assigns a unique request ID to each request (reads ``X-Request-ID``
      header if present, otherwise generates a UUID4).
    - Logs request start/end with method, path, status code, and duration.
    - Stores the request ID in the context variable so all log lines within
      the same request carry it automatically.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self._logger = get_logger("http")

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Extract or generate request ID.
        headers = dict(scope.get("headers", []))
        request_id = (
            headers.get(b"x-request-id", b"").decode() or str(uuid.uuid4())
        )
        set_request_id(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        method = scope.get("method", "WS")
        path = scope.get("path", "/")
        start_time = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                # Inject request ID into response headers.
                headers_list = list(message.get("headers", []))
                headers_list.append(
                    (b"x-request-id", request_id.encode())
                )
                message = {**message, "headers": headers_list}
            await send(message)

        self._logger.info(
            "request.started",
            method=method,
            path=path,
        )

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # pragma: no cover
            self._logger.exception(
                "request.failed",
                method=method,
                path=path,
                error=str(exc),
            )
            raise
        finally:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log_fn = self._logger.warning if status_code >= 400 else self._logger.info
            log_fn(
                "request.completed",
                method=method,
                path=path,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            structlog.contextvars.clear_contextvars()


# ---------------------------------------------------------------------------
# Performance decorator helper
# ---------------------------------------------------------------------------


def log_performance(logger: structlog.stdlib.BoundLogger, operation: str) -> Callable:
    """
    Decorator that logs the execution time of an async or sync function.

    Usage::

        @log_performance(logger, "compute_score")
        async def compute_score(...):
            ...
    """
    import asyncio
    import functools

    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = await func(*args, **kwargs)
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    logger.debug(
                        "performance.measured",
                        operation=operation,
                        duration_ms=duration_ms,
                    )
                    return result
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    logger.warning(
                        "performance.error",
                        operation=operation,
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                    raise

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    logger.debug(
                        "performance.measured",
                        operation=operation,
                        duration_ms=duration_ms,
                    )
                    return result
                except Exception as exc:
                    duration_ms = round((time.perf_counter() - start) * 1000, 2)
                    logger.warning(
                        "performance.error",
                        operation=operation,
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                    raise

            return sync_wrapper

    return decorator
