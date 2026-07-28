"""
Property Nearby Places API (Sprint 3): Geo-connected neighborhood landmarks.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.models.realty_enterprise import PropertyNearbyPlace
from app.schemas.property_enterprise import PropertyNearbyPlaceSchema

router = APIRouter()


@router.post("/properties/{property_id}/nearby", response_model=PropertyNearbyPlaceSchema, status_code=201)
def add_nearby_place(
    property_id: int,
    data: PropertyNearbyPlaceSchema,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Add a neighborhood landmark (Metro, Tech Park, Hospital, School, Mall)."""
    item = PropertyNearbyPlace(
        property_id=property_id,
        category=data.category,
        name=data.name,
        distance=data.distance,
        travel_time=data.travel_time,
        google_rating=data.google_rating,
        map_link=data.map_link,
        latitude=data.latitude,
        longitude=data.longitude,
        created_by=str(current_user.id),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/properties/{property_id}/nearby", response_model=List[PropertyNearbyPlaceSchema])
def list_nearby_places(
    property_id: int,
    db: Session = Depends(get_mysql_db),
):
    """List all nearby places for a property."""
    return (
        db.query(PropertyNearbyPlace)
        .filter(PropertyNearbyPlace.property_id == property_id, PropertyNearbyPlace.is_deleted == False)
        .order_by(PropertyNearbyPlace.category.asc(), PropertyNearbyPlace.id.asc())
        .all()
    )


@router.put("/nearby/{place_id}", response_model=PropertyNearbyPlaceSchema)
def update_nearby_place(
    place_id: int,
    data: PropertyNearbyPlaceSchema,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Edit an existing nearby place."""
    item = db.query(PropertyNearbyPlace).filter(PropertyNearbyPlace.id == place_id, PropertyNearbyPlace.is_deleted == False).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nearby place not found")

    for k, v in data.model_dump(exclude_unset=True).items():
        if hasattr(item, k):
            setattr(item, k, v)
    item.updated_by = str(current_user.id)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/nearby/{place_id}", status_code=204)
def delete_nearby_place(
    place_id: int,
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.admin_or_employee_required),
):
    """Soft delete a nearby place."""
    item = db.query(PropertyNearbyPlace).filter(PropertyNearbyPlace.id == place_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Nearby place not found")
    item.is_deleted = True
    item.updated_by = str(current_user.id)
    db.commit()
    return None
