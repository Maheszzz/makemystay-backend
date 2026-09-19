"""
"""

from fastapi import APIRouter

from app.api.admin.operations import router as operations_router
from app.api.admin.reviews import router as reviews_router

admin_router = APIRouter(tags=["Admin / Operations"])
admin_router.include_router(operations_router)
admin_router.include_router(reviews_router)

__all__ = ["admin_router"]
