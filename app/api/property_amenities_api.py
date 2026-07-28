"""
Property Amenities API (Sprint 3): Amenity Master and Property Amenity assignment.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.models.realty_enterprise import AmenityMaster, PropertyAmenity
from app.schemas.property_enterprise import AmenityMasterSchema, PropertyAmenitySchema

router = APIRouter()


@router.post("/amenities/master", response_model=AmenityMasterSchema, status_code=201)
def create_master_amenity(
    data: AmenityMasterSchema,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Add a new custom amenity to the Master Amenity database."""
    existing = db.query(AmenityMaster).filter(AmenityMaster.code == data.code, AmenityMaster.is_deleted == False).first()
    if existing:
        raise HTTPException(status_code=400, detail="Amenity code already exists")

    amenity = AmenityMaster(
        code=data.code,
        name=data.name,
        category=data.category or "Room",
        icon_url=data.icon_url,
        created_by=str(current_user.id),
    )
    db.add(amenity)
    db.commit()
    db.refresh(amenity)
    return amenity


@router.get("/amenities/master", response_model=List[AmenityMasterSchema])
def list_master_amenities(
    category: str = None,
    db: Session = Depends(get_mysql_db),
):
    """List all available master amenities, optionally filtered by category."""
    query = db.query(AmenityMaster).filter(AmenityMaster.is_deleted == False)
    if category:
        query = query.filter(AmenityMaster.category == category)
    return query.order_by(AmenityMaster.category.asc(), AmenityMaster.name.asc()).all()


@router.post("/properties/{property_id}/amenities", response_model=PropertyAmenitySchema, status_code=201)
def assign_property_amenity(
    property_id: int,
    data: PropertyAmenitySchema,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Assign an amenity to a property."""
    prop_amenity = PropertyAmenity(
        property_id=property_id,
        amenity_id=data.amenity_id,
        custom_label=data.custom_label,
        is_custom=data.is_custom,
        created_by=str(current_user.id),
    )
    db.add(prop_amenity)
    db.commit()
    db.refresh(prop_amenity)
    return prop_amenity


@router.get("/properties/{property_id}/amenities", response_model=List[PropertyAmenitySchema])
def list_property_amenities(
    property_id: int,
    db: Session = Depends(get_mysql_db),
):
    """Get all assigned amenities for a property."""
    return (
        db.query(PropertyAmenity)
        .filter(PropertyAmenity.property_id == property_id, PropertyAmenity.is_deleted == False)
        .all()
    )


@router.delete("/properties/{property_id}/amenities/{amenity_id}", status_code=204)
def unassign_property_amenity(
    property_id: int,
    amenity_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Remove an assigned amenity from a property."""
    item = (
        db.query(PropertyAmenity)
        .filter(PropertyAmenity.property_id == property_id, PropertyAmenity.id == amenity_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Property amenity not found")
    item.is_deleted = True
    item.updated_by = str(current_user.id)
    db.commit()
    return None
