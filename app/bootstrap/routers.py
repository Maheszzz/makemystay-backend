"""
Central FastAPI router registration — single place to see all HTTP surface area.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.api.agent_routes import router as agent_router
from app.api.admin import admin_router
from app.api.auth import router as auth_router
from app.api.demo import router as demo_router
from app.api.payment import router as payment_router, razorpay_webhook
from app.api.realty import realty_router
from app.api.retell import retell_router
from app.api.seo import seo_router
from app.api.upload import router as upload_router

from app.api.websockets import ws_router
from app.api.properties_enterprise import router as properties_enterprise_router
from app.api.property_media import router as property_media_router
from app.api.property_amenities_api import router as property_amenities_router
from app.api.property_nearby_api import router as property_nearby_router
from app.api.property_analytics_api import router as property_analytics_router


API_PREFIX = "/api/v1"


def register_routers(app: FastAPI) -> None:
    """Mount all API routers on the application."""
    app.include_router(seo_router)
    app.include_router(realty_router, prefix=API_PREFIX)
    app.include_router(auth_router, prefix=API_PREFIX)
    app.include_router(upload_router, prefix=API_PREFIX)
    app.include_router(payment_router, prefix=API_PREFIX)

    # Razorpay webhook at root so dashboards can POST /payments/webhook without /api/v1
    webhook_alias = APIRouter()
    webhook_alias.add_api_route(
        "/payments/webhook",
        razorpay_webhook,
        methods=["POST"],
        include_in_schema=False,
    )
    app.include_router(webhook_alias)

    app.include_router(demo_router, prefix=API_PREFIX)
    app.include_router(retell_router, prefix=API_PREFIX)


    app.include_router(admin_router, prefix=f"{API_PREFIX}/admin")

    app.include_router(ws_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)


    # Phase 3 – Enterprise Real Estate CMS Routers (Sprints 3, 5, 6, 7, 8, 9, 10 + 3 Special Features)
    app.include_router(properties_enterprise_router, prefix=API_PREFIX, tags=["Enterprise Properties"])
    app.include_router(property_media_router, prefix=API_PREFIX, tags=["Property Media & Documents"])
    app.include_router(property_amenities_router, prefix=API_PREFIX, tags=["Property Amenities"])
    app.include_router(property_nearby_router, prefix=API_PREFIX, tags=["Property Nearby Places"])
    app.include_router(property_analytics_router, prefix=API_PREFIX, tags=["Property Analytics & Leads"])
