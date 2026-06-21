"""Realty API endpoints for Contacts, Properties, and Property Images."""

from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.config import settings
from app.core.exceptions import DatabaseError, NotFoundException
from app.repo import realty as realty_repo
from app.utils.property_image_mime import (
    ALLOWED_IMAGE_MIME_TYPES,
    derive_image_content_type_from_url,
    normalize_content_type_for_compare,
    verify_s3_object_head,
)
from app.utils.s3_client import get_s3_client
from app.utils.s3_magic_bytes import detect_image_mime_from_s3_range
from app.services.upload_alerts import emit_upload_event, increment_upload_counter
from app.services.property_list_cache import (
    bump_properties_list_cache,
    get_cached_properties_list,
    properties_list_cache_key,
    set_cached_properties_list,
)
from app.utils.property_seo_narrative import build_property_seo_about
from app.schemas.realty import (
    ContactCreate,
    ContactResponse,
    ContactStatus,
    ContactUpdate,
    ListingType,
    PropertyCategoryTab,
    PropertyCreate,
    PropertyImageCreate,
    PropertyImageResponse,
    PropertyImageUpdate,
    PropertyListItem,
    PropertyResponse,
    PaginatedPropertyResponse,
    PropertyType,
    PropertyUpdate,
    ReviewCreate,
    ReviewResponse,
    LocalityTrustStatsResponse,
    SearchSuggestionsResponse,
)

realty_router = APIRouter(tags=["Realty"])


def _property_response_from_orm(property_obj) -> PropertyResponse:
    """ORM row → PropertyResponse, with server-generated long-form `seo_about` for PDP SEO."""
    p = PropertyResponse.model_validate(property_obj)
    return p.model_copy(update={"seo_about": build_property_seo_about(property_obj)})


def _merge_head_and_mime_for_image_url(url: str) -> Tuple[str, bool, Optional[int]]:
    """URL-derived MIME + optional S3 HEAD (retries), optional libmagic Range GET, delete policy."""
    derived = derive_image_content_type_from_url(url)
    content_type = derived
    mime_validated = True
    size_from_head: Optional[int] = None
    if not settings.S3_VERIFY_UPLOAD_CONTENT_TYPE_WITH_HEAD:
        return content_type, mime_validated, size_from_head
    client = get_s3_client()
    bucket = settings.S3_BUCKET_NAME
    hr = verify_s3_object_head(
        image_url=url,
        derived_content_type=derived,
        bucket=bucket,
        s3_client=client,
    )
    if hr.ok and hr.s3_content_length is not None:
        size_from_head = hr.s3_content_length

    magic_mime: Optional[str] = None
    if (
        hr.ok
        and settings.S3_VERIFY_MAGIC_FROM_BYTES
        and client
        and bucket
        and hr.key
    ):
        magic_mime = detect_image_mime_from_s3_range(
            client,
            bucket,
            hr.key,
            max_bytes=max(256, settings.S3_MAGIC_RANGE_BYTES),
        )

    overridden = False
    if magic_mime and magic_mime in ALLOWED_IMAGE_MIME_TYPES:
        content_type = magic_mime
        overridden = True
    elif (
        hr.ok
        and settings.S3_HEAD_VERIFY_OVERRIDE_DB_FROM_S3
        and hr.s3_content_type
        and hr.s3_content_type in ALLOWED_IMAGE_MIME_TYPES
    ):
        content_type = hr.s3_content_type
        overridden = True

    policy_type = magic_mime if (magic_mime and magic_mime in ALLOWED_IMAGE_MIME_TYPES) else hr.s3_content_type
    pt = normalize_content_type_for_compare(policy_type) if policy_type else ""
    mismatch = bool(hr.ok and pt and pt != normalize_content_type_for_compare(derived))

    if hr.ok and mismatch:
        increment_upload_counter("s3_head_mismatch")

    if hr.ok and mismatch:
        if (
            settings.S3_HEAD_MISMATCH_DELETE_OBJECT
            and not overridden
            and hr.key
            and client
            and bucket
        ):
            should_delete = True
            if settings.S3_HEAD_DELETE_REQUIRES_DOUBLE_CONFIRM:
                hr2 = verify_s3_object_head(
                    image_url=url,
                    derived_content_type=derived,
                    bucket=bucket,
                    s3_client=client,
                )
                s1 = normalize_content_type_for_compare(hr.s3_content_type)
                s2 = normalize_content_type_for_compare(hr2.s3_content_type) if hr2.ok else ""
                if not hr2.ok:
                    should_delete = False
                    increment_upload_counter("s3_head_double_confirm_aborted")
                    emit_upload_event(
                        "s3_head_delete_aborted_second_head_failed",
                        key=hr.key,
                        error=hr2.error,
                    )
                elif not hr2.mismatch:
                    should_delete = False
                    increment_upload_counter("s3_head_double_confirm_aborted")
                    emit_upload_event(
                        "s3_head_delete_aborted_second_head_ok",
                        key=hr.key,
                    )
                    if hr2.s3_content_type and hr2.s3_content_type in ALLOWED_IMAGE_MIME_TYPES:
                        content_type = hr2.s3_content_type
                        mime_validated = True
                        overridden = True
                elif s1 != s2:
                    should_delete = False
                    increment_upload_counter("s3_head_double_confirm_aborted")
                    emit_upload_event(
                        "s3_head_delete_aborted_head_disagree",
                        key=hr.key,
                        first=s1,
                        second=s2,
                    )

            if should_delete:
                try:
                    client.delete_object(Bucket=bucket, Key=hr.key)
                except Exception as e:
                    logger.error("S3 delete_object on mismatch failed: {}", e)
                    raise HTTPException(
                        status_code=500,
                        detail="Could not remove invalid upload.",
                    ) from e
                increment_upload_counter("s3_head_delete_on_mismatch")
                emit_upload_event("s3_head_delete_on_mismatch", key=hr.key)
                raise HTTPException(
                    status_code=400,
                    detail="Uploaded object Content-Type does not match the URL extension; object was removed.",
                )
        if settings.S3_HEAD_MISMATCH_STRICT and not overridden:
            mime_validated = False
    return content_type, mime_validated, size_from_head


# ==================== CONTACT ENDPOINTS ====================


@realty_router.get("/realty/contacts", response_model=List[ContactResponse])
def list_contacts(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        100, ge=1, le=100, description="Maximum number of records to return"
    ),
    status: Optional[ContactStatus] = Query(
        None, description="Filter by contact status"
    ),
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.get_current_user),
):
    """
    List all contacts with pagination and optional status filter.

    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum records to return (default: 100, max: 100)
    - **status**: Filter by status (new, contacted, closed)
    """
    contacts = realty_repo.get_contacts(
        db, skip=skip, limit=limit, status=status.value if status else None
    )
    return contacts


@realty_router.get("/realty/contacts/{contact_id}", response_model=ContactResponse)
def get_contact(contact_id: int, db: Session = Depends(get_mysql_db), current_user=Depends(security.get_current_user)):
    """
    Get a specific contact by ID.

    - **contact_id**: The unique identifier of the contact
    """
    contact = realty_repo.get_contact_by_id(db, contact_id)
    if not contact:
        raise NotFoundException("Contact", contact_id)
    return contact


@realty_router.post("/realty/contacts", response_model=ContactResponse, status_code=201)
def create_contact(
    contact: ContactCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_mysql_db),
):
    """
    Create a new contact.

    - **name**: Contact name (required, 1-100 chars)
    - **phone**: Phone number (required, 10-15 chars)
    - **email**: Email address (required, valid email format)
    - **message**: Message content (required, max 250 chars)
    - **status**: Contact status (optional, defaults to 'new')
    """
    try:
        new_contact = realty_repo.create_contact(db, contact.model_dump(by_alias=False))

        from app.services.contact_notifications import run_contact_notifications
        
        # Always use BackgroundTasks to guarantee execution (bypassing Redis worker dependency)
        background_tasks.add_task(
            run_contact_notifications,
            contact.model_dump(by_alias=False),
            new_contact.id
        )
        logger.info(f"Contact #{new_contact.id} queued via FastAPI BackgroundTasks to guarantee execution")

        return new_contact
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to create contact: {str(e)}")


@realty_router.put("/realty/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    contact_id: int, contact: ContactUpdate, db: Session = Depends(get_mysql_db), current_user=Depends(security.get_current_user)
):
    """
    Update an existing contact.

    - **contact_id**: The unique identifier of the contact
    - Only provided fields will be updated
    """
    db_contact = realty_repo.get_contact_by_id(db, contact_id)
    if not db_contact:
        raise NotFoundException("Contact", contact_id)

    try:
        return realty_repo.update_contact(
            db, db_contact, contact.model_dump(exclude_unset=True, by_alias=False)
        )
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to update contact: {str(e)}")


@realty_router.delete("/realty/contacts/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_mysql_db), current_user=Depends(security.get_current_user)):
    """
    Delete a contact.

    - **contact_id**: The unique identifier of the contact
    """
    db_contact = realty_repo.get_contact_by_id(db, contact_id)
    if not db_contact:
        raise NotFoundException("Contact", contact_id)

    try:
        realty_repo.delete_contact(db, db_contact)
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to delete contact: {str(e)}")
    return None


# ==================== PROPERTY ENDPOINTS ====================


@realty_router.get("/realty/properties", response_model=PaginatedPropertyResponse)
def list_properties(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(
        24, ge=1, le=100, description="Maximum number of records to return (default 24 for listing pages)"
    ),
    category: Optional[PropertyCategoryTab] = Query(
        None,
        description="Admin UI tab: pg | rent | buy | plot (server-side filter; overrides property_type / listing_type)",
    ),
    property_type: Optional[PropertyType] = Query(
        None, description="Filter by property type"
    ),
    listing_type: Optional[ListingType] = Query(
        None, description="Filter by listing type"
    ),
    is_available: Optional[bool] = Query(None, description="Filter by availability"),
    search: Optional[str] = Query(
        None, description="Search by name, location or description"
    ),
    exclude_property_type: Optional[str] = Query(
        None, description="Exclude a specific property type"
    ),
    min_price: Optional[float] = Query(None, description="Minimum price"),
    max_price: Optional[float] = Query(None, description="Maximum price"),
    city: Optional[str] = Query(None, description="Filter by city"),
    sort_by: Optional[str] = Query(
        "review_count_desc",
        description="Sort by: review_count_desc, rating_desc, price_asc, price_desc, newest",
    ),
    db: Session = Depends(get_mysql_db),
):
    """
    List all properties with pagination and filters.

    Returns a slim payload (no full description or review bodies; one hero image per row).

    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum records to return (default: 24, max: 100)
    - **category**: Tab filter — PG (property_type PG), PLOT (Plot), RENT (rent listings excluding PG/Plot), BUY (buy listings excluding PG/Plot)
    - **property_type**: Filter by type (PG, 1RK, 1BHK, 2BHK) — ignored if **category** is set
    - **listing_type**: Filter by listing (buy, rent) — ignored if **category** is set
    - **is_available**: Filter by availability (true/false)
    - **search**: Search string for name, location or description
    - **exclude_property_type**: Exclude a specific type (e.g., PG) — ignored if **category** is set
    - **min_price**: Minimum price
    - **max_price**: Maximum price
    - **city**: Filter by city
    - **sort_by**: Sort order (default: review_count_desc)
    """
    pt = property_type.value if property_type else None
    lt = listing_type.value if listing_type else None
    ex = exclude_property_type
    if category is not None:
        pt = None
        lt = None
        ex = None

    cache_payload = {
        "skip": skip,
        "limit": limit,
        "category": category.value if category else None,
        "property_type": pt,
        "listing_type": lt,
        "is_available": is_available,
        "search": search,
        "exclude_property_type": ex,
        "min_price": min_price,
        "max_price": max_price,
        "city": city,
        "sort_by": sort_by,
    }
    cache_key = properties_list_cache_key(cache_payload)
    cached = get_cached_properties_list(cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    properties, total = realty_repo.get_properties(
        db,
        skip=skip,
        limit=limit,
        property_type=pt,
        listing_type=lt,
        is_available=is_available,
        search=search,
        exclude_property_type=ex,
        category=category.value if category else None,
        min_price=min_price,
        max_price=max_price,
        city=city,
        sort_by=sort_by,
        list_mode=True,
    )
    items = [
        PropertyListItem.model_validate(p).model_dump(mode="json") for p in properties
    ]

    # Tab badges must respect the same city/search/price filters as the listing query.
    property_counts = realty_repo.get_property_category_counts(
        db,
        is_available=is_available,
        search=search,
        min_price=min_price,
        max_price=max_price,
        city=city,
    )

    payload = {
        "items": items, 
        "total": total,
        "property_counts": property_counts,
    }
    set_cached_properties_list(cache_key, payload)
    return JSONResponse(content=payload)


@realty_router.get("/realty/properties/suggestions", response_model=SearchSuggestionsResponse)
def get_property_suggestions(
    q: str = Query(..., min_length=1, description="Search term for suggestions"),
    db: Session = Depends(get_mysql_db),
):
    """
    Autocomplete grouped by property names and areas/landmarks.

    - **q**: The search term (minimum 1 character)
    """
    return realty_repo.get_property_suggestions(db, q)


@realty_router.get("/realty/properties/{property_id}/similar", response_model=PaginatedPropertyResponse)
def list_similar_properties(
    property_id: int,
    limit: int = Query(
        6,
        ge=1,
        le=12,
        description="Max similar listings (default 6, max 12)",
    ),
    db: Session = Depends(get_mysql_db),
):
    """
    Similar listings for a property detail page: locality + neighbor areas first, then broader same-category fill.

    Not cached (property-specific; low volume).
    """
    out = realty_repo.get_similar_properties(db, property_id, limit=limit)
    if out is None:
        raise NotFoundException("Property", property_id)
    properties, total = out
    items = [
        PropertyListItem.model_validate(p).model_dump(mode="json") for p in properties
    ]
    return JSONResponse(content={"items": items, "total": total})


@realty_router.get("/realty/properties/{property_id}", response_model=PropertyResponse)
def get_property(property_id: int, db: Session = Depends(get_mysql_db)):
    """
    Get a specific property by ID with its images.

    - **property_id**: The unique identifier of the property
    """
    property_obj = realty_repo.get_property_by_id(db, property_id)
    if not property_obj:
        raise NotFoundException("Property", property_id)
    return _property_response_from_orm(property_obj)


@realty_router.get(
    "/realty/properties/by-slug/{property_type}/{slug}", response_model=PropertyResponse
)
def get_property_by_slug(
    property_type: str, slug: str, db: Session = Depends(get_mysql_db)
):
    """
    Get a specific property by type and slug.

    - **property_type**: The type of the property (e.g., pg, rent)
    - **slug**: The auto-generated slug of the property
    """
    property_obj = realty_repo.get_property_by_slug(db, property_type, slug)
    if not property_obj:
        raise NotFoundException("Property", f"{property_type}/{slug}")
    return _property_response_from_orm(property_obj)


@realty_router.post(
    "/realty/properties", response_model=PropertyResponse, status_code=201
)
def create_property(
    property_data: PropertyCreate,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Create a new property.

    - **property_name**: Property name (required)
    - **location**: Location (required)
    - **property_type**: Type (PG, 1RK, 1BHK, 2BHK - required)
    - **listing_type**: Listing type (buy, rent - defaults to rent)
    """
    try:
        out = realty_repo.create_property(db, property_data.model_dump())
        bump_properties_list_cache()
        return _property_response_from_orm(out)
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to create property: {str(e)}")


@realty_router.put("/realty/properties/{property_id}", response_model=PropertyResponse)
def update_property(
    property_id: int,
    property_data: PropertyUpdate,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Update an existing property.

    - **property_id**: The unique identifier of the property
    - Only provided fields will be updated
    """
    db_property = realty_repo.get_property_by_id(db, property_id)
    if not db_property:
        raise NotFoundException("Property", property_id)

    try:
        out = realty_repo.update_property(
            db, db_property, property_data.model_dump(exclude_unset=True)
        )
        realty_repo.touch_property_verified(db, property_id)
        bump_properties_list_cache()
        return _property_response_from_orm(out)
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to update property: {str(e)}")


@realty_router.delete("/realty/properties/{property_id}", status_code=204)
def delete_property(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Delete a property and its associated images.

    - **property_id**: The unique identifier of the property
    """
    db_property = realty_repo.get_property_by_id(db, property_id)
    if not db_property:
        raise NotFoundException("Property", property_id)

    try:
        realty_repo.delete_property(db, db_property)
        bump_properties_list_cache()
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to delete property: {str(e)}")
    return None


@realty_router.post(
    "/realty/properties/{property_id}/restore", response_model=PropertyResponse
)
def restore_property(
    property_id: int,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Restore a soft-deleted property.
    """
    db_property = realty_repo.get_property_by_id(db, property_id, include_deleted=True)
    if not db_property:
        raise NotFoundException("Property", property_id)

    try:
        out = realty_repo.restore_property(db, db_property)
        bump_properties_list_cache()
        return _property_response_from_orm(out)
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to restore property: {str(e)}")


# ==================== PROPERTY IMAGE ENDPOINTS ====================


@realty_router.get(
    "/realty/properties/{property_id}/images",
    response_model=List[PropertyImageResponse],
)
def list_property_images(property_id: int, db: Session = Depends(get_mysql_db)):
    """
    List all images for a specific property.

    - **property_id**: The unique identifier of the property
    """
    # Verify property exists
    property_obj = realty_repo.get_property_by_id(db, property_id)
    if not property_obj:
        raise NotFoundException("Property", property_id)

    return realty_repo.get_property_images(db, property_id)


@realty_router.post(
    "/realty/properties/{property_id}/images",
    response_model=PropertyImageResponse,
    status_code=201,
)
def add_property_image(
    property_id: int,
    image: PropertyImageCreate,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Add a new image to a property.

    - **property_id**: The unique identifier of the property
    - **image_url**: URL of the image (required)
    - **is_primary**: Whether this is the primary image (default: false)
    - **sort_order**: Display order (default: 0)
    """
    # Verify property exists
    property_obj = realty_repo.get_property_by_id(db, property_id)
    if not property_obj:
        raise NotFoundException("Property", property_id)

    try:
        payload = image.model_dump()
        url = payload["image_url"]
        content_type, mime_validated, size_from_head = _merge_head_and_mime_for_image_url(url)
        payload["content_type"] = content_type
        payload["mime_validated"] = mime_validated
        if payload.get("file_size") is None and size_from_head is not None:
            payload["file_size"] = size_from_head
        out = realty_repo.create_property_image(db, payload, property_id)
        bump_properties_list_cache()
        return out
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to add property image: {str(e)}")


@realty_router.put("/realty/images/{image_id}", response_model=PropertyImageResponse)
def update_property_image(
    image_id: int,
    image: PropertyImageUpdate,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Update a property image.

    - **image_id**: The unique identifier of the image
    - Only provided fields will be updated
    """
    db_image = realty_repo.get_property_image_by_id(db, image_id)
    if not db_image:
        raise NotFoundException("Image", image_id)

    try:
        update_data = image.model_dump(exclude_unset=True)
        if "image_url" in update_data:
            u = update_data["image_url"]
            ct, mv, sz_h = _merge_head_and_mime_for_image_url(u)
            update_data["content_type"] = ct
            update_data["mime_validated"] = mv
            if update_data.get("file_size") is None and sz_h is not None:
                update_data["file_size"] = sz_h
        out = realty_repo.update_property_image(db, db_image, update_data)
        bump_properties_list_cache()
        return out
    except HTTPException:
        raise
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to update property image: {str(e)}")


@realty_router.delete("/realty/images/{image_id}", status_code=204)
def delete_property_image(
    image_id: int,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Delete a property image.

    - **image_id**: The unique identifier of the image
    """
    db_image = realty_repo.get_property_image_by_id(db, image_id)
    if not db_image:
        raise NotFoundException("Image", image_id)

    try:
        realty_repo.delete_property_image(db, db_image)
        bump_properties_list_cache()
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to delete property image: {str(e)}")
    return None


# ==================== REVIEW ENDPOINTS ====================


@realty_router.get(
    "/realty/properties/{property_id}/reviews", response_model=List[ReviewResponse]
)
def list_property_reviews(property_id: int, db: Session = Depends(get_mysql_db)):
    """
    List all reviews for a specific property.

    - **property_id**: The unique identifier of the property
    """
    # Verify property exists
    property_obj = realty_repo.get_property_by_id(db, property_id)
    if not property_obj:
        raise NotFoundException("Property", property_id)

    return realty_repo.get_reviews_by_property_id(db, property_id)


@realty_router.post(
    "/realty/properties/{property_id}/reviews",
    response_model=ReviewResponse,
    status_code=201,
)
def add_property_review(
    property_id: int, review: ReviewCreate, db: Session = Depends(get_mysql_db)
):
    """
    Add a new review to a property.

    - **property_id**: The unique identifier of the property
    - **rating**: Rating from 1 to 5 (required)
    - **user_name**: Name of the user (required)
    - **comment**: Review comment (optional)
    """
    # Verify property exists
    property_obj = realty_repo.get_property_by_id(db, property_id)
    if not property_obj:
        raise NotFoundException("Property", property_id)

    try:
        payload = review.model_dump(exclude_none=True)
        out = realty_repo.create_review(db, payload, property_id)
        bump_properties_list_cache()
        return out
    except SQLAlchemyError as e:
        raise DatabaseError(f"Failed to add review: {str(e)}")


@realty_router.get(
    "/realty/localities/{slug}/trust-stats",
    response_model=LocalityTrustStatsResponse,
)
def locality_trust_stats(slug: str, db: Session = Depends(get_mysql_db)):
    """
    Aggregated ratings and verified counts for a Bangalore locality hub slug.
    Used for locality QuickAnswer, headers, and JSON-LD.
    """
    name = slug.replace("-", " ").title()
    if slug == "hsr-layout":
        name = "HSR Layout"
    elif slug == "btm":
        name = "BTM Layout"
    stats = realty_repo.get_locality_trust_stats(db, slug.lower(), name)
    return LocalityTrustStatsResponse(**stats)
