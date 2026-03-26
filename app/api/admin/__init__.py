"""
Admin API: composed from operations (sync, jobs, WhatsApp, payments) and CRM (leads, RMs, funnel).
"""

from fastapi import APIRouter

from app.api.admin.crm import router as crm_router
from app.api.admin.lead_import import router as lead_import_router
from app.api.admin.operations import router as operations_router

admin_router = APIRouter(tags=["Admin / Operations"])
admin_router.include_router(operations_router)
admin_router.include_router(crm_router)
admin_router.include_router(lead_import_router)

__all__ = ["admin_router"]
