"""API endpoints for Administrative operations."""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.repo import admin as admin_repo
from app.schemas.admin import DashboardStats, GlobalSearchResponse
from app.schemas.lead import LeadResponse

admin_router = APIRouter(tags=["Admin Dashboard"])

@admin_router.get(
    "/admin/dashboard/stats",
    response_model=DashboardStats,
    summary="Get high-level dashboard metrics",
)
def get_dashboard_stats(
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Returns aggregated metrics for the dashboard:
    - Total leads
    - Total properties
    - Total contacts
    - AI calls triggered
    - Active listings
    """
    return admin_repo.get_dashboard_stats(db)

@admin_router.get(
    "/admin/leads/live",
    response_model=List[LeadResponse],
    summary="Get recent live leads",
)
def get_live_leads(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Returns the most recent leads for the live activity feed.
    """
    return admin_repo.get_live_leads(db, limit=limit)

@admin_router.get(
    "/admin/search",
    response_model=GlobalSearchResponse,
    summary="Global search for properties and leads",
)
def global_search(
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Search across properties and leads.
    """
    return admin_repo.global_search(db, query=q)
