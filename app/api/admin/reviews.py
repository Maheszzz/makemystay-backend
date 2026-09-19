"""Admin review moderation."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.exceptions import DatabaseError, NotFoundException
from app.repo import realty as realty_repo
from app.schemas.realty import ReviewModerateUpdate, ReviewResponse, ReviewStatus
from app.services.property_list_cache import bump_properties_list_cache

router = APIRouter(prefix="/reviews", tags=["Admin / Reviews"])


@router.get("", response_model=List[ReviewResponse])
def list_reviews_for_moderation(
    status: ReviewStatus = ReviewStatus.pending,
    limit: int = 50,
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_required),
):
    return realty_repo.get_reviews_for_moderation(db, status.value, limit=limit)


@router.patch("/{review_id}", response_model=ReviewResponse)
def moderate_review(
    review_id: int,
    body: ReviewModerateUpdate,
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_required),
):
    try:
        out = realty_repo.moderate_review(
            db,
            review_id,
            status=body.status.value,
            owner_response=body.owner_response,
            verified_stay=body.verified_stay,
        )
        if not out:
            raise NotFoundException("Review", review_id)
        bump_properties_list_cache(out.property_id, out.property.slug if out.property else None)
        return out
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to moderate review: {str(e)}")


@router.post("/properties/{property_id}/verify", status_code=204)
def mark_property_verified(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_required),
):
    prop = realty_repo.get_property_by_id(db, property_id)
    if not prop:
        raise NotFoundException("Property", property_id)
    realty_repo.touch_property_verified(db, property_id)
    bump_properties_list_cache(prop.id, prop.slug)
