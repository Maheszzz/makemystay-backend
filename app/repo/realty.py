import re
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy import desc, func, or_, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, attributes, joinedload, selectinload

from app.models.realty import Contact, Property, PropertyImage, Review


def execute_with_retry(fn: Callable[[], Any], retries: int = 3, delay: float = 1.0) -> Any:
    """Robust wrapper for database operations to handle transient OperationalErrors."""
    for i in range(retries):
        try:
            return fn()
        except OperationalError as exc:
            if i == retries - 1:
                from loguru import logger
                logger.error(f"Database operation failed after {retries} attempts: {exc}")
                raise
            time.sleep(delay)


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


def _is_transient_mysql_connection_lost(exc: Exception) -> bool:
    """2006 / 2013 — stale pool or dropped connection (common with Docker MySQL)."""
    orig = getattr(exc, "orig", None)
    if orig is None and getattr(exc, "__cause__", None) is not None:
        orig = exc.__cause__
    args = getattr(orig, "args", ()) if orig is not None else ()
    if args and args[0] in (2006, 2013):
        return True
    msg = str(exc).lower()
    return "lost connection" in msg or "gone away" in msg


def _invalidate_session_connection(db: Session) -> None:
    """Drop bad pooled connection so the next query checks out a fresh one."""
    try:
        db.rollback()
    except Exception:
        pass
    try:
        db.connection().invalidate()
    except Exception:
        pass


def _query_all_with_connection_retry(db: Session, query, skip: int, limit: int):
    """Run list query; retry once after invalidate on transient MySQL disconnect."""
    # Legacy wrapper; preferring execute_with_retry for new code.
    return execute_with_retry(lambda: query.offset(skip).limit(limit).all())


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
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    city: Optional[str] = None,
    sort_by: Optional[str] = "rating_desc",
    include_deleted: bool = False,
    list_mode: bool = True,
) -> Tuple[List[Property], int]:
    """Retrieve properties with filters and eager-loaded images and reviews.

    When ``category`` is set (pg|rent|buy|plot), it drives the filter and overrides
    ``property_type`` / ``listing_type`` / ``exclude_property_type`` (callers should omit those).

    ``list_mode=True`` (default): one image per row, no review rows loaded; ratings from materialized columns.
    """
    from sqlalchemy import or_

    query = db.query(Property)
    if not list_mode:
        query = query.options(selectinload(Property.reviews))

    # Apply Filters
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

    if city:
        # Match against the dedicated city column (exact if normalized, or ilike as fallback)
        query = query.filter(or_(Property.city == city.lower(), Property.location.ilike(f"%{city}%")))

    if min_price is not None:
        query = query.filter(Property.starting_price >= min_price)
    if max_price is not None:
        query = query.filter(Property.starting_price <= max_price)

    if search:
        search_parts = [s.strip().lower() for s in search.split(",") if s.strip()]
        search_terms = []
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

    # Apply Sorting
    if sort_by == "price_asc":
        query = query.order_by(Property.starting_price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(Property.starting_price.desc())
    elif sort_by == "newest":
        query = query.order_by(Property.created_at.desc())
    else:  # rating_desc (default)
        query = query.order_by(desc(func.coalesce(Property.average_rating, 0)))

    # Set query statement timeout to 5 seconds to prevent hanging
    try:
        db.execute(text("SET SESSION MAX_EXECUTION_TIME = 5000")) # MySQL 5.7.8+ format
    except Exception:
        pass

    try:
        properties = _query_all_with_connection_retry(db, query, skip, limit)
        # Use optimized count query instead of query.count() which is slow in SQLAlchemy
        count_q = query.with_entities(func.count(Property.id)).order_by(None)
        total_count = execute_with_retry(lambda: count_q.scalar())
    except OperationalError as exc:
        if not _is_missing_soft_delete_column_error(exc):
            raise

        # Fallback for environments where migrations are not yet applied.
        fallback_query = db.query(Property)
        if not list_mode:
            fallback_query = fallback_query.options(selectinload(Property.reviews))

        if category:
            fallback_query = _apply_property_category_tab(fallback_query, category)
        else:
            if property_type:
                fallback_query = fallback_query.filter(Property.property_type == property_type)
            if exclude_property_type:
                fallback_query = fallback_query.filter(Property.property_type != exclude_property_type)
            if listing_type:
                fallback_query = fallback_query.filter(Property.listing_type == listing_type)

        if is_available is not None:
            fallback_query = fallback_query.filter(Property.is_available == is_available)
        if city:
            fallback_query = fallback_query.filter(or_(Property.city == city.lower(), Property.location.ilike(f"%{city}%")))
        if min_price is not None:
            fallback_query = fallback_query.filter(Property.starting_price >= min_price)
        if max_price is not None:
            fallback_query = fallback_query.filter(Property.starting_price <= max_price)

        if search:
            search_parts = [s.strip().lower() for s in search.split(",") if s.strip()]
            search_terms = []
            for part in search_parts:
                search_terms.append(part)
            conditions = []
            for term in set(search_terms):
                search_filter = f"%{term}%"
                conditions.append(Property.property_name.ilike(search_filter))
                conditions.append(Property.location.ilike(search_filter))
            fallback_query = fallback_query.filter(or_(*conditions))

        if sort_by == "price_asc":
            fallback_query = fallback_query.order_by(Property.starting_price.asc())
        elif sort_by == "price_desc":
            fallback_query = fallback_query.order_by(Property.starting_price.desc())
        elif sort_by == "newest":
            fallback_query = fallback_query.order_by(Property.created_at.desc())
        else:
            fallback_query = fallback_query.order_by(desc(func.coalesce(Property.average_rating, 0)))

        properties = _query_all_with_connection_retry(db, fallback_query, skip, limit)
        total_count = fallback_query.count()

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

    return properties, total_count


# Bangalore micro-areas — reused for "similar property" locality expansion (keep in sync with get_properties search).
_SIMILAR_NEARBY_LOCALITIES: Dict[str, List[str]] = {
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


def _similar_locality_terms(location: Optional[str]) -> List[str]:
    """First segment of location + neighbor areas (same idea as listing search)."""
    if not location or not str(location).strip():
        return []
    first = str(location).split(",")[0].strip().lower()
    if not first:
        return []
    terms: set = {first}
    for key, neighbors in _SIMILAR_NEARBY_LOCALITIES.items():
        if key in first or first in key:
            terms.add(key)
            terms.update(neighbors)
    return list(terms)


def get_similar_properties(
    db: Session,
    property_id: int,
    limit: int = 6,
) -> Optional[Tuple[List[Property], int]]:
    """Similar listings for PDP: same tab as source (PG or same type), locality + neighbors then broader fill.

    Returns ``None`` if the source property does not exist or is deleted.
    """
    src = (
        db.query(Property)
        .filter(Property.id == property_id)
        .filter(func.coalesce(Property.is_deleted, False) == False)  # noqa: E712
        .first()
    )
    if not src:
        return None

    is_pg = (src.property_type or "").lower() == "pg"

    def base_query():
        q = db.query(Property).filter(func.coalesce(Property.is_deleted, False) == False)  # noqa: E712
        q = q.filter(Property.id != property_id)
        if is_pg:
            q = _apply_property_category_tab(q, "pg")
        else:
            if src.property_type:
                q = q.filter(Property.property_type == src.property_type)
            if src.listing_type:
                q = q.filter(Property.listing_type == src.listing_type)
        return q

    terms = _similar_locality_terms(src.location)
    results: List[Property] = []
    seen_ids: set = set()

    try:
        db.execute(text("SET SESSION MAX_EXECUTION_TIME = 5000"))
    except Exception:
        pass

    if terms:
        q1 = base_query()
        q1 = q1.filter(or_(*[Property.location.ilike(f"%{t}%") for t in terms]))
        q1 = q1.order_by(desc(func.coalesce(Property.average_rating, 0)))
        stage1 = execute_with_retry(lambda: q1.limit(limit).all())
        results.extend(stage1)
        seen_ids.update(p.id for p in results)

    remaining = limit - len(results)
    if remaining > 0:
        q2 = base_query()
        if seen_ids:
            q2 = q2.filter(~Property.id.in_(seen_ids))
        q2 = q2.order_by(desc(func.coalesce(Property.average_rating, 0)))
        stage2 = execute_with_retry(lambda: q2.limit(remaining).all())
        results.extend(stage2)

    _attach_property_images_bulk(db, results, max_per_property=1)
    for p in results:
        if p.average_rating is not None:
            p.average_rating = float(p.average_rating)
        if p.review_count is None:
            p.review_count = 0
        attributes.set_committed_value(p, "reviews", [])

    return results, len(results)


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
        name_q = (
            db.query(Property.property_name)
            .filter(Property.property_name.ilike(search_filter))
            .distinct()
            .limit(5)
        )
        if False: # include_deleted is not defined here, defaulting to False behavior
            name_q = name_q.filter(func.coalesce(Property.is_deleted, False) == False)

        try:
            results = execute_with_retry(lambda: name_q.all())
            names.extend(results)
        except OperationalError as exc:
            if not _is_missing_soft_delete_column_error(exc):
                raise
            # Fallback for missing soft-delete col
            fallback_q = db.query(Property.property_name).filter(Property.property_name.ilike(search_filter)).distinct().limit(5)
            names.extend(execute_with_retry(lambda: fallback_q.all()))

        # Get unique locations
        loc_q = (
            db.query(Property.location)
            .filter(Property.location.ilike(search_filter))
            .distinct()
            .limit(5)
        )
        if False: # include_deleted is not defined here, defaulting to False behavior
            loc_q = loc_q.filter(func.coalesce(Property.is_deleted, False) == False)

        try:
            results = execute_with_retry(lambda: loc_q.all())
            locations.extend(results)
        except OperationalError as exc:
            if not _is_missing_soft_delete_column_error(exc):
                raise
            fallback_q = db.query(Property.location).filter(Property.location.ilike(search_filter)).distinct().limit(5)
            locations.extend(execute_with_retry(lambda: fallback_q.all()))

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


def _slugify_fragment(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


def _build_property_slug_source(
    name: Optional[str],
    property_type: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    ordered_tokens: List[str] = []
    for fragment in (name, property_type, location):
        cleaned = _slugify_fragment(fragment)
        if not cleaned:
            continue
        for token in cleaned.split("-"):
            if token and token not in ordered_tokens:
                ordered_tokens.append(token)
    return "-".join(ordered_tokens)


def generate_unique_slug(
    db: Session,
    name: str,
    property_type: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    base_slug = _build_property_slug_source(name, property_type, location) or _slugify_fragment(name)
    slug = base_slug
    counter = 1
    while db.query(Property).filter(Property.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1
    return slug


def create_property(db: Session, property_data: dict) -> Property:
    """Create a new property with transaction safety."""
    if not property_data.get("slug") and property_data.get("property_name"):
        property_data["slug"] = generate_unique_slug(
            db,
            property_data["property_name"],
            property_data.get("property_type"),
            property_data.get("location"),
        )

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
