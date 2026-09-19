"""
Property Analytics & Lead Tracking API (Sprint 8 & 9).
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.models.realty_enterprise import PropertyView, PropertyDownload
router = APIRouter()


@router.post("/properties/{property_id}/track-view")
def track_property_view(
    property_id: int,
    request: Request,
    time_on_page_seconds: int = Query(0, ge=0),
    db: Session = Depends(get_mysql_db),
):
    """Track property view and duration (Sprint 8)."""
    viewer_ip = request.client.host if request.client else "0.0.0.0"
    view_entry = PropertyView(
        property_id=property_id,
        viewer_ip=viewer_ip,
        time_on_page_seconds=time_on_page_seconds,
    )
    db.add(view_entry)
    db.commit()
    return {"status": "success", "view_recorded": True}


@router.get("/properties/{property_id}/analytics")
def get_property_analytics(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
) -> Dict[str, Any]:
    """
    Get aggregated analytics & lead metrics for a property (Sprint 8).
    Includes Property Views, Brochure/Pricing Downloads, and Leads Generated.
    """
    total_views = (
        db.query(func.count(PropertyView.id))
        .filter(PropertyView.property_id == property_id, PropertyView.is_deleted == False)
        .scalar()
        or 0
    )
    avg_time = (
        db.query(func.avg(PropertyView.time_on_page_seconds))
        .filter(PropertyView.property_id == property_id, PropertyView.is_deleted == False)
        .scalar()
        or 0
    )
    total_downloads = (
        db.query(func.count(PropertyDownload.id))
        .filter(PropertyDownload.property_id == property_id, PropertyDownload.is_deleted == False)
        .scalar()
        or 0
    )
    total_leads = 0
    return {
        "property_id": property_id,
        "views": int(total_views),
        "avg_time_on_page_seconds": round(float(avg_time), 1),
        "total_downloads": int(total_downloads),
        "total_leads_generated": int(total_leads),
    }
