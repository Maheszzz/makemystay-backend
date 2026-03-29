"""Repository layer for Realty models with transaction safety."""

import re
from collections import defaultdict
from typing import Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, attributes, joinedload, selectinload

from app.models.realty import Contact, Property, PropertyImage, Review


def refresh_property_review_stats(db: Session, property_id: int) -> None:
    """Recompute materialized avg_rating / review_count from the reviews table."""
    r = (
        db.query(func.avg(Review.rating), func.count(Review.id))
        .filter(Review.property_id == property_id)
        .first()
    )
    avg_v, cnt_v = (r[0], r[1]) if r else (None, 0)
    cnt = int(cnt_v or 0)
    avg_float = float(avg_v) if cnt and avg_v is not None else None
    try:
        db.query(Property).filter(Property.id == property_id).update(
            {
                Property.average_rating: avg_float,
                Property.review_count: cnt,
            },
            synchronize_session=False,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def _attach_property_images_bulk(
    db: Session,
    properties: List[Property],
    max_per_property: Optional[int] = None,
) -> None:
    """Load images for many properties in one query.

    ``selectinload``/``subqueryload`` on list queries has been unreliable in production
    (list returned ``images: []`` while ``get_property_by_id`` had full galleries).
    Attaching rows explicitly matches detail behaviour and avoids N+1 queries.

    ``max_per_property`` (e.g. 1 for public list) caps payload size; order prefers primary then sort_order.
    """
    if not properties:
        return
    pids = [p.id for p in properties]
    rows = (
        db.query(PropertyImage)
        .filter(PropertyImage.property_id.in_(pids))
        .filter(func.coalesce(PropertyImage.is_deleted, False) == False)  # noqa: E712
        .order_by(
            PropertyImage.property_id,
            PropertyImage.is_primary.desc(),
            PropertyImage.sort_order,
            PropertyImage.id,
        )
        .all()
    )
    by_pid: Dict[int, List[PropertyImage]] = defaultdict(list)
    for img in rows:
        by_pid[img.property_id].append(img)
    for p in properties:
        imgs = by_pid.get(p.id, [])
        if max_per_property is not None and len(imgs) > max_per_property:
            imgs = imgs[:max_per_property]
        attributes.set_committed_value(p, "images", imgs)

def _is_missing_soft_delete_column_error(exc: Exception) -> bool:
    """Detect MySQL errors caused by missing legacy soft-delete columns."""
    msg = str(exc).lower()
    return "unknown column" in msg and "is_deleted" in msg


# ==================== CONTACT REPO ====================


def get_contacts(
    db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None
) -> List[Contact]:
    """Retrieve contacts with optional status filter and pagination."""
    query = db.query(Contact)
    if status:
        query = query.filter(Contact.status == status)
    return query.offset(skip).limit(limit).all()


def get_contact_by_id(db: Session, contact_id: int) -> Optional[Contact]:
    """Retrieve a single contact by ID."""
    return db.query(Contact).filter(Contact.id == contact_id).first()


def create_contact(db: Session, contact_data: dict) -> Contact:
    """Create a new contact with transaction safety."""
    try:
        db_contact = Contact(**contact_data)
        db.add(db_contact)
        db.commit()
        db.refresh(db_contact)
        
        # Trigger Retell AI outbound call asynchronously after 10 seconds
        try:
            from app.tasks.lead_tasks import enqueue_call_task
            enqueue_call_task.apply_async(
                args=[db_contact.id, db_contact.phone, db_contact.name_],
                countdown=10
            )
        except Exception as e:
            from loguru import logger
            logger.error(f"Failed to enqueue AI call for contact {db_contact.id}: {str(e)}")

        return db_contact
    except SQLAlchemyError:
        db.rollback()
        raise


def update_contact(db: Session, db_contact: Contact, update_data: dict) -> Contact:
    """Update an existing contact with transaction safety."""
    try:
        for field, value in update_data.items():
            setattr(db_contact, field, value)
        db.commit()
        db.refresh(db_contact)
        return db_contact
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_contact(db: Session, db_contact: Contact) -> None:
    """Delete a contact with transaction safety."""
    try:
        db.delete(db_contact)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


# ==================== PROPERTY REPO ====================


def _apply_property_category_tab(query, category: Optional[str]):
    """Filter by UI tab (pg / rent / buy / plot) — matches PropertyResponse.derive_category logic."""
    if not category:
        return query
    c = category.strip().lower()
    if c == "pg":
        return query.filter(func.lower(Property.property_type) == "pg")
    if c == "plot":
        return query.filter(func.lower(Property.property_type) == "plot")
    if c == "rent":
        return query.filter(Property.listing_type == "rent").filter(
            ~func.lower(Property.property_type).in_(["pg", "plot"])
        )
    if c == "buy":
        return query.filter(Property.listing_type == "buy").filter(
            ~func.lower(Property.property_type).in_(["pg", "plot"])
        )
    return query


def get_properties(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    property_type: Optional[str] = None,
    listing_type: Optional[str] = None,
    is_available: Optional[bool] = None,
    search: Optional[str] = None,
    exclude_property_type: Optional[str] = None,
    category: Optional[str] = None,
    include_deleted: bool = False,
    list_mode: bool = True,
) -> List[Property]:
    """Retrieve properties with filters and eager-loaded images and reviews.

    When ``category`` is set (pg|rent|buy|plot), it drives the filter and overrides
    ``property_type`` / ``listing_type`` / ``exclude_property_type`` (callers should omit those).

    ``list_mode=True`` (default): one image per row, no review rows loaded; ratings from materialized columns.
    """
    from sqlalchemy import or_

    query = db.query(Property)
    if not list_mode:
        query = query.options(selectinload(Property.reviews))
    query = query.order_by(desc(func.coalesce(Property.average_rating, 0)))

    # Treat NULL as not deleted for legacy rows
    if not include_deleted:
        query = query.filter(func.coalesce(Property.is_deleted, False) == False)  # noqa: E712

    if category:
        query = _apply_property_category_tab(query, category)
    else:
        if property_type:
            query = query.filter(Property.property_type == property_type)
        if exclude_property_type:
            query = query.filter(Property.property_type != exclude_property_type)
        if listing_type:
            query = query.filter(Property.listing_type == listing_type)
    if is_available is not None:
        query = query.filter(Property.is_available == is_available)
    if search:
        search_parts = [s.strip().lower() for s in search.split(",") if s.strip()]
        search_terms = []

        # Simple nearby mapping for Bangalore areas
        NEARBY_MAPPING = {
            "electronic city": ["bommasandra", "chandapura", "begur", "hebbagodi"],
            "bommasandra": ["electronic city", "chandapura", "hebbagodi"],
            "hsr layout": ["koramangala", "btm layout", "bellandur", "bommanahalli"],
            "koramangala": ["hsr layout", "btm layout", "indiranagar", "ejipura"],
            "whitefield": ["marathahalli", "bellandur", "mahadevapura", "itpl"],
            "marathahalli": [
                "whitefield",
                "bellandur",
                "kadubeesanahalli",
                "munnekollal",
            ],
            "indiranagar": ["koramangala", "domlur", "hal", "cv raman nagar"],
            "btm layout": ["hsr layout", "koramangala", "jayanagar", "jp nagar"],
            "jayanagar": ["btm layout", "jp nagar", "basavanagudi", "banashankari"],
            "jp nagar": [
                "jayanagar",
                "btm layout",
                "bannerghatta road",
                "banashankari",
            ],
        }

        for part in search_parts:
            search_terms.append(part)
            for key, neighbors in NEARBY_MAPPING.items():
                if key in part or part in key:
                    search_terms.extend(neighbors)

        conditions = []
        for term in set(search_terms):
            search_filter = f"%{term}%"
            conditions.append(Property.property_name.ilike(search_filter))
            conditions.append(Property.location.ilike(search_filter))

        query = query.filter(or_(*conditions))

    try:
        properties = query.offset(skip).limit(limit).all()
    except OperationalError as exc:
        if not _is_missing_soft_delete_column_error(exc):
            raise

        # Fallback for environments where migrations are not yet applied.
        fallback_query = db.query(Property)
        if not list_mode:
            fallback_query = fallback_query.options(selectinload(Property.reviews))
        fallback_query = fallback_query.order_by(
            desc(func.coalesce(Property.average_rating, 0))
        )
        if category:
            fallback_query = _apply_property_category_tab(fallback_query, category)
        else:
            if property_type:
                fallback_query = fallback_query.filter(Property.property_type == property_type)
            if exclude_property_type:
                fallback_query = fallback_query.filter(
                    Property.property_type != exclude_property_type
                )
            if listing_type:
                fallback_query = fallback_query.filter(Property.listing_type == listing_type)
        if is_available is not None:
            fallback_query = fallback_query.filter(Property.is_available == is_available)
        if search:
            search_parts = [s.strip().lower() for s in search.split(",") if s.strip()]
            search_terms = []
            NEARBY_MAPPING = {
                "electronic city": ["bommasandra", "chandapura", "begur", "hebbagodi"],
                "bommasandra": ["electronic city", "chandapura", "hebbagodi"],
                "hsr layout": ["koramangala", "btm layout", "bellandur", "bommanahalli"],
                "koramangala": ["hsr layout", "btm layout", "indiranagar", "ejipura"],
                "whitefield": ["marathahalli", "bellandur", "mahadevapura", "itpl"],
                "marathahalli": [
                    "whitefield",
                    "bellandur",
                    "kadubeesanahalli",
                    "munnekollal",
                ],
                "indiranagar": ["koramangala", "domlur", "hal", "cv raman nagar"],
                "btm layout": ["hsr layout", "koramangala", "jayanagar", "jp nagar"],
                "jayanagar": ["btm layout", "jp nagar", "basavanagudi", "banashankari"],
                "jp nagar": [
                    "jayanagar",
                    "btm layout",
                    "bannerghatta road",
                    "banashankari",
                ],
            }
            for part in search_parts:
                search_terms.append(part)
                for key, neighbors in NEARBY_MAPPING.items():
                    if key in part or part in key:
                        search_terms.extend(neighbors)
            conditions = []
            for term in set(search_terms):
                search_filter = f"%{term}%"
                conditions.append(Property.property_name.ilike(search_filter))
                conditions.append(Property.location.ilike(search_filter))
            fallback_query = fallback_query.filter(or_(*conditions))

        properties = fallback_query.offset(skip).limit(limit).all()

    if list_mode:
        _attach_property_images_bulk(db, properties, max_per_property=1)
        for p in properties:
            if p.average_rating is not None:
                p.average_rating = float(p.average_rating)
            if p.review_count is None:
                p.review_count = 0
            attributes.set_committed_value(p, "reviews", [])
    else:
        _attach_property_images_bulk(db, properties)
        for p in properties:
            p.review_count = len(p.reviews)
            p.average_rating = (
                sum(r.rating for r in p.reviews) / p.review_count
                if p.review_count > 0
                else 0.0
            )

    return properties


def get_property_suggestions(db: Session, q: str) -> List[str]:
    """Retrieve unique property names and locations matching the search term."""
    q_parts = [s.strip().lower() for s in q.split(",") if s.strip()]
    if not q_parts:
        return []

    # Get suggestions for the LAST typed part of the query
    current_q = q_parts[-1]

    search_terms = [current_q]

    # Simple nearby mapping for Bangalore
    NEARBY_MAPPING = {
        "electronic city": ["bommasandra", "chandapura", "begur", "hebbagodi"],
        "bommasandra": ["electronic city", "chandapura", "hebbagodi"],
        "hsr layout": ["koramangala", "btm layout", "bellandur", "bommanahalli"],
        "koramangala": ["hsr layout", "btm layout", "indiranagar", "ejipura"],
        "whitefield": ["marathahalli", "bellandur", "mahadevapura", "itpl"],
        "marathahalli": ["whitefield", "bellandur", "kadubeesanahalli", "munnekollal"],
        "indiranagar": ["koramangala", "domlur", "hal", "cv raman nagar"],
        "btm layout": ["hsr layout", "koramangala", "jayanagar", "jp nagar"],
        "jayanagar": ["btm layout", "jp nagar", "basavanagudi", "banashankari"],
        "jp nagar": ["jayanagar", "btm layout", "bannerghatta road", "banashankari"],
    }

    for key, neighbors in NEARBY_MAPPING.items():
        if key in current_q or current_q in key:
            search_terms.extend(neighbors)

    names = []
    locations = []
    for term in set(search_terms):
        search_filter = f"%{term}%"

        # Get unique property names
        try:
            names.extend(
                db.query(Property.property_name)
                .filter(
                    Property.property_name.ilike(search_filter),
                    func.coalesce(Property.is_deleted, False) == False,  # noqa: E712
                )
                .distinct()
                .limit(5)
                .all()
            )
        except OperationalError as exc:
            if not _is_missing_soft_delete_column_error(exc):
                raise
            names.extend(
                db.query(Property.property_name)
                .filter(Property.property_name.ilike(search_filter))
                .distinct()
                .limit(5)
                .all()
            )

        # Get unique locations
        try:
            locations.extend(
                db.query(Property.location)
                .filter(
                    Property.location.ilike(search_filter),
                    func.coalesce(Property.is_deleted, False) == False,  # noqa: E712
                )
                .distinct()
                .limit(5)
                .all()
            )
        except OperationalError as exc:
            if not _is_missing_soft_delete_column_error(exc):
                raise
            locations.extend(
                db.query(Property.location)
                .filter(Property.location.ilike(search_filter))
                .distinct()
                .limit(5)
                .all()
            )

    # Extract strings and combine
    suggestions = [n[0] for n in names] + [loc[0] for loc in locations]

    # Return unique sorted results
    return sorted(list(set(suggestions)))


def get_property_by_id(
    db: Session, property_id: int, include_deleted: bool = False
) -> Optional[Property]:
    """Retrieve a single property by ID with eager-loaded images and reviews."""
    query = (
        db.query(Property)
        .options(joinedload(Property.images), joinedload(Property.reviews))
        .filter(Property.id == property_id)
    )

    if not include_deleted:
        query = query.filter(func.coalesce(Property.is_deleted, False) == False)  # noqa: E712

    try:
        p = query.first()
    except OperationalError as exc:
        if not _is_missing_soft_delete_column_error(exc):
            raise
        p = (
            db.query(Property)
            .options(joinedload(Property.images), joinedload(Property.reviews))
            .filter(Property.id == property_id)
            .first()
        )

    if p:
        p.review_count = len(p.reviews)
        p.average_rating = (
            sum(r.rating for r in p.reviews) / p.review_count
            if p.review_count > 0
            else 0.0
        )

    return p


def get_property_by_slug(
    db: Session, property_type: str, slug: str, include_deleted: bool = False
) -> Optional[Property]:
    """Retrieve a single property by type and slug with eager-loaded images and reviews."""
    query = (
        db.query(Property)
        .options(joinedload(Property.images), joinedload(Property.reviews))
        .filter(Property.slug == slug)
    )

    if not include_deleted:
        query = query.filter(func.coalesce(Property.is_deleted, False) == False)  # noqa: E712

    try:
        p = query.first()
    except OperationalError as exc:
        if not _is_missing_soft_delete_column_error(exc):
            raise
        p = (
            db.query(Property)
            .options(joinedload(Property.images), joinedload(Property.reviews))
            .filter(Property.slug == slug)
            .first()
        )

    if p:
        p.review_count = len(p.reviews)
        p.average_rating = (
            sum(r.rating for r in p.reviews) / p.review_count
            if p.review_count > 0
            else 0.0
        )

    return p


def generate_unique_slug(db: Session, name: str) -> str:
    base_slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").lower()
    slug = base_slug
    counter = 1
    while db.query(Property).filter(Property.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def create_property(db: Session, property_data: dict) -> Property:
    """Create a new property with transaction safety."""
    if not property_data.get("slug") and property_data.get("property_name"):
        property_data["slug"] = generate_unique_slug(db, property_data["property_name"])

    try:
        db_property = Property(**property_data)
        db.add(db_property)
        db.commit()
        db.refresh(db_property)
        return db_property
    except SQLAlchemyError:
        db.rollback()
        raise


def update_property(db: Session, db_property: Property, update_data: dict) -> Property:
    """Update an existing property with transaction safety."""
    try:
        for field, value in update_data.items():
            setattr(db_property, field, value)
        db.commit()
        db.refresh(db_property)
        return db_property
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_property(db: Session, db_property: Property, soft: bool = True) -> None:
    """Delete a property (soft delete by default)."""
    try:
        if soft:
            db_property.is_deleted = True
            # Also soft delete images
            for img in db_property.images:
                img.is_deleted = True
        else:
            db.delete(db_property)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def restore_property(db: Session, db_property: Property) -> Property:
    """Restore a soft-deleted property."""
    try:
        db_property.is_deleted = False
        # Also restore images? User might want this.
        for img in db_property.images:
            img.is_deleted = False
        db.commit()
        db.refresh(db_property)
        return db_property
    except SQLAlchemyError:
        db.rollback()
        raise


# ==================== PROPERTY IMAGE REPO ====================


def get_property_images(db: Session, property_id: int) -> List[PropertyImage]:
    """Retrieve all images for a property, ordered by sort_order."""
    return (
        db.query(PropertyImage)
        .filter(PropertyImage.property_id == property_id)
        .order_by(PropertyImage.sort_order)
        .all()
    )


def get_property_image_by_id(db: Session, image_id: int) -> Optional[PropertyImage]:
    """Retrieve a single property image by ID."""
    return db.query(PropertyImage).filter(PropertyImage.id == image_id).first()


def create_property_image(
    db: Session, image_data: dict, property_id: int
) -> PropertyImage:
    """Create a new property image with transaction safety. Deletes existing duplicate if present."""
    try:
        # Check for existing image with same URL for this property
        existing_img = (
            db.query(PropertyImage)
            .filter(
                PropertyImage.property_id == property_id,
                PropertyImage.image_url == image_data["image_url"],
            )
            .first()
        )

        if existing_img:
            db.delete(existing_img)
            # flush to ensure deletion happens before insertion if there's a unique constraint
            db.flush()

        db_image = PropertyImage(**image_data, property_id=property_id)
        db.add(db_image)
        db.commit()
        db.refresh(db_image)
        return db_image
    except SQLAlchemyError:
        db.rollback()
        raise


def update_property_image(
    db: Session, db_image: PropertyImage, update_data: dict
) -> PropertyImage:
    """Update an existing property image with transaction safety."""
    try:
        for field, value in update_data.items():
            setattr(db_image, field, value)
        db.commit()
        db.refresh(db_image)
        return db_image
    except SQLAlchemyError:
        db.rollback()
        raise


def delete_property_image(db: Session, db_image: PropertyImage) -> None:
    """Delete a property image with transaction safety."""
    try:
        db.delete(db_image)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


# ==================== REVIEW REPO ====================


def get_reviews_by_property_id(db: Session, property_id: int) -> List[Review]:
    """Retrieve all reviews for a property."""
    return (
        db.query(Review)
        .filter(Review.property_id == property_id)
        .order_by(Review.created_at.desc())
        .all()
    )


def create_review(db: Session, review_data: dict, property_id: int) -> Review:
    """Create a new review with transaction safety."""
    try:
        # Automatically populate property_name if not provided
        if not review_data.get("property_name"):
            prop = db.query(Property).filter(Property.id == property_id).first()
            if prop:
                review_data["property_name"] = prop.property_name

        db_review = Review(**review_data, property_id=property_id)
        db.add(db_review)
        db.commit()
        db.refresh(db_review)
        refresh_property_review_stats(db, property_id)
        return db_review
    except SQLAlchemyError:
        db.rollback()
        raise
