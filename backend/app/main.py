"""
FastAPI application factory and entry point for the BI-Platform backend.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import close_db, init_db
from app.core.exceptions import register_exception_handlers

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application version
# ---------------------------------------------------------------------------

APP_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Storage directory initialisation
# ---------------------------------------------------------------------------


def init_storage_dirs() -> None:
    """Create all local storage directories required at runtime."""
    dirs = [
        settings.STORAGE_BASE_DIR,
        settings.SCREENSHOT_DIR,
        settings.EXPORT_DIR,
    ]
    for d in dirs:
        path = Path(d)
        path.mkdir(parents=True, exist_ok=True)
        logger.debug("storage_dir_ready path=%s", path.resolve())


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ---- startup ----
    logger.info("startup: initialising database …")
    await init_db()

    logger.info("startup: ensuring storage directories exist …")
    init_storage_dirs()

    logger.info("startup: BI-Platform %s ready", APP_VERSION)
    yield

    # ---- shutdown ----
    logger.info("shutdown: closing database connections …")
    await close_db()
    logger.info("shutdown: complete")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    app = FastAPI(
        title=settings.APP_NAME,
        version=APP_VERSION,
        description=(
            "BI-Platform API — business intelligence, website auditing, "
            "and discovery engine."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ------------------------------------------------------------------
    # Middleware
    # ------------------------------------------------------------------

    # CORS — must be added before any routing middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=settings.CORS_ALLOW_METHODS,
        allow_headers=settings.CORS_ALLOW_HEADERS,
    )

    # GZip compression for responses > 1 KB
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    register_exception_handlers(app)

    # ------------------------------------------------------------------
    # Static files
    # ------------------------------------------------------------------

    screenshot_path = Path(settings.SCREENSHOT_DIR)
    screenshot_path.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/static/screenshots",
        StaticFiles(directory=str(screenshot_path)),
        name="screenshots",
    )

    # ------------------------------------------------------------------
    # API routers
    # ------------------------------------------------------------------

    from app.api.v1.router import api_router  # noqa: PLC0415

    app.include_router(api_router)

    # ------------------------------------------------------------------
    # Built-in utility endpoints
    # ------------------------------------------------------------------

    @app.get("/health", tags=["system"], summary="Health check")
    async def health_check() -> dict:
        return {
            "status": "ok",
            "version": APP_VERSION,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }

    @app.get("/", include_in_schema=False)
    async def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    # ------------------------------------------------------------------
    # Prometheus metrics
    # ------------------------------------------------------------------

    try:
        from prometheus_client import (  # noqa: PLC0415
            CONTENT_TYPE_LATEST,
            generate_latest,
        )
        from fastapi.responses import Response  # noqa: PLC0415

        @app.get(
            "/metrics",
            tags=["system"],
            summary="Prometheus metrics",
            include_in_schema=False,
        )
        async def metrics() -> Response:
            return Response(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )

    except ImportError:
        logger.warning(
            "prometheus_client not installed — /metrics endpoint disabled."
        )

    return app


# ---------------------------------------------------------------------------
# Module-level app instance (used by uvicorn / gunicorn workers)
# ---------------------------------------------------------------------------

app: FastAPI = create_app()
