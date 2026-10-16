"""
Main API v1 router — aggregates all endpoint sub-routers.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.businesses import router as businesses_router
from app.api.v1.endpoints.contacts import router as contacts_router
from app.api.v1.endpoints.crm import router as crm_router
from app.api.v1.endpoints.discovery import router as discovery_router
from app.api.v1.endpoints.audits import router as audits_router
from app.api.v1.endpoints.analytics import router as analytics_router
from app.api.v1.endpoints.outreach import router as outreach_router
from app.api.v1.endpoints.proposals import router as proposals_router
from app.api.v1.endpoints.export import router as export_router
from app.api.v1.endpoints.freelance import router as freelance_router
from app.api.v1.endpoints.websocket import router as websocket_router

api_router = APIRouter(prefix="/api/v1")

# Auth
api_router.include_router(auth_router)

# Core domain
api_router.include_router(businesses_router)
api_router.include_router(contacts_router)
api_router.include_router(discovery_router)
api_router.include_router(freelance_router)
api_router.include_router(audits_router)
api_router.include_router(analytics_router)

# CRM & Outreach
api_router.include_router(crm_router)
api_router.include_router(outreach_router)
api_router.include_router(proposals_router)

# Export
api_router.include_router(export_router)

# WebSocket (no /api/v1 prefix – kept at root for WS client simplicity)
api_router.include_router(websocket_router)
