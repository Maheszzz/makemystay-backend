"""
Central FastAPI router registration — single place to see all HTTP surface area.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.api.agent_routes import router as agent_router
from app.api.admin import admin_router
from app.api.auth import router as auth_router
from app.api.demo import router as demo_router
from app.api.acres import acres_router
from app.api.housing import housing_router
from app.api.internal_ops import router as internal_ops_router
from app.api.meta_whatsapp import meta_whatsapp_router
from app.api.payment import router as payment_router, razorpay_webhook
from app.api.realty import realty_router
from app.api.retell import retell_router
from app.api.seo import seo_router
from app.api.upload import router as upload_router
from app.api.webhooks import webhooks_router
from app.api.whatsapp import whatsapp_router
from app.api.websockets import ws_router


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
    app.include_router(housing_router, prefix=API_PREFIX)
    app.include_router(acres_router, prefix=API_PREFIX)
    app.include_router(whatsapp_router, prefix=API_PREFIX)
    app.include_router(meta_whatsapp_router, prefix=API_PREFIX)

    app.include_router(webhooks_router, prefix=API_PREFIX)
    app.include_router(webhooks_router)

    app.include_router(admin_router, prefix=f"{API_PREFIX}/admin")
    
    app.include_router(ws_router, prefix=API_PREFIX)
    app.include_router(agent_router, prefix=API_PREFIX)
    app.include_router(internal_ops_router, prefix=API_PREFIX)
