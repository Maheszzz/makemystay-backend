"""
Enterprise Real Estate API Router (Sprints 3, 5, 6, 7, 10 + 3 Special Features).
Provides comprehensive REST CRUD, Publish Workflow, Version History Audit Logs,
Unit Availability, and Unified Single-Response Public Website payload.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.models.realty import Property
from app.models.realty_enterprise import PropertyAuditLog
from app.repo.property_enterprise_repo import (
    create_property_enterprise,
    get_property_by_id_or_slug,
    list_properties_enterprise,
    restore_property,
    soft_delete_property,
    transition_property_status,
    update_property_enterprise,
)
from app.schemas.property_enterprise import (
    CreatePropertyRequest,
    PropertyAuditLogSchema,
    PropertyDetailResponse,
    PropertyStatusEnum,
    PropertyStatusTransitionRequest,
    UpdatePropertyRequest,
)

router = APIRouter()


# ==================== PUBLIC UNIFIED WEBSITE API (SPRINT 10) ====================

@router.get("/public/properties/{slug}", response_model=PropertyDetailResponse)
def get_public_property_by_slug(
    slug: str,
    type: Optional[str] = None,
    db: Session = Depends(get_mysql_db),
):
    """
    Sprint 10 Unified Public Website Endpoint:
    Returns everything needed for a property page in a single response:
    Basic Info, Pricing, Images, Videos, Amenities, Nearby Places, Sales Kit, SEO, Share Data,
    Reviews, Units, Tags, and Audit status.
    Strictly restricted to properties where status == 'published' and is_deleted == False.
    """
    prop = get_property_by_id_or_slug(db, slug, include_deleted=False)
    if not prop or prop.status != "published":
        raise HTTPException(status_code=404, detail="Published property not found")
    return prop


# ==================== ADMIN / ENTERPRISE CMS CRUD (SPRINTS 3, 5, 6, 7) ====================

@router.post("/properties", response_model=PropertyDetailResponse, status_code=201)
@router.post("/enterprise/properties", response_model=PropertyDetailResponse, status_code=201)
def create_enterprise_property(
    data: CreatePropertyRequest,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Create a new property listing with nested enterprise modules and initial audit log."""
    prop = create_property_enterprise(
        db=db,
        data=data,
        current_user_id=current_user.id,
        current_user_name=getattr(current_user, "email", "Admin"),
    )
    return get_property_by_id_or_slug(db, prop.id, include_deleted=False)


@router.get("/properties", response_model=List[PropertyDetailResponse])
@router.get("/enterprise/properties", response_model=List[PropertyDetailResponse])
def list_enterprise_properties(
    status: Optional[str] = Query(None, description="Filter by status: draft, pending_review, approved, published, archived"),
    visibility: Optional[str] = Query(None, description="Filter by visibility: public, private, draft"),
    category: Optional[str] = Query(None, description="Filter by category: PG, Rental, Buy, Commercial"),
    tag: Optional[str] = Query(None, description="Filter by tag name (e.g. Near Metro)"),
    locality: Optional[str] = Query(None, description="Filter by locality/area"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """List properties with dynamic filtering by status, category, tag, locality."""
    items, _ = list_properties_enterprise(
        db=db,
        status=status,
        visibility=visibility,
        category=category,
        tag=tag,
        locality=locality,
        skip=skip,
        limit=limit,
    )
    return items


@router.get("/properties/{id_or_slug}", response_model=PropertyDetailResponse)
@router.get("/enterprise/properties/{id_or_slug}", response_model=PropertyDetailResponse)
def get_enterprise_property_detail(
    id_or_slug: str,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Get complete single-response payload for admin property review & editing."""
    prop = get_property_by_id_or_slug(db, id_or_slug, include_deleted=False)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    return prop


@router.put("/properties/{property_id}", response_model=PropertyDetailResponse)
@router.put("/enterprise/properties/{property_id}", response_model=PropertyDetailResponse)
def update_enterprise_property(
    property_id: int,
    data: UpdatePropertyRequest,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Update property fields, bump version number, and log changes snapshot."""
    prop = update_property_enterprise(
        db=db,
        property_id=property_id,
        data=data,
        current_user_id=current_user.id,
        current_user_name=getattr(current_user, "email", "Admin"),
    )
    return get_property_by_id_or_slug(db, prop.id, include_deleted=False)


@router.delete("/properties/{property_id}", status_code=204)
@router.delete("/enterprise/properties/{property_id}", status_code=204)
def delete_enterprise_property(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_required),
):
    """Soft delete property — data is never permanently erased."""
    soft_delete_property(db, property_id=property_id, current_user_id=current_user.id)
    return None


@router.post("/properties/{property_id}/restore", response_model=PropertyDetailResponse)
@router.post("/enterprise/properties/{property_id}/restore", response_model=PropertyDetailResponse)
def restore_enterprise_property(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_required),
):
    """Restore a soft-deleted property back to draft status."""
    prop = restore_property(db, property_id=property_id, current_user_id=current_user.id)
    return get_property_by_id_or_slug(db, prop.id, include_deleted=False)


@router.post("/properties/{property_id}/publish", response_model=PropertyDetailResponse)
@router.post("/realty/properties/{property_id}/publish", response_model=PropertyDetailResponse)
@router.post("/enterprise/properties/{property_id}/publish", response_model=PropertyDetailResponse)
def publish_workflow_transition(
    property_id: int,
    data: PropertyStatusTransitionRequest,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """
    Sprint 6 Property Publish Workflow:
    Draft -> Pending Review -> Approved -> Published -> Archived.
    Bumps version number and logs workflow status transition.
    """
    prop = transition_property_status(
        db=db,
        property_id=property_id,
        new_status=data.status,
        reason=data.reason,
        current_user_id=current_user.id,
    )
    return get_property_by_id_or_slug(db, prop.id, include_deleted=False)


@router.get("/properties/{property_id}/audit-logs", response_model=List[PropertyAuditLogSchema])
@router.get("/enterprise/properties/{property_id}/audit-logs", response_model=List[PropertyAuditLogSchema])
def get_property_version_history(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """
    Special Feature #1: Version History & Audit Logs.
    Returns timestamped list of all changes, versions, and JSON snapshots for the property.
    """
    return (
        db.query(PropertyAuditLog)
        .filter(PropertyAuditLog.property_id == property_id, PropertyAuditLog.is_deleted == False)
        .order_by(PropertyAuditLog.version_number.desc(), PropertyAuditLog.id.desc())
        .all()
    )
