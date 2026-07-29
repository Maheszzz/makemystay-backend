"""
Enterprise Repository Layer for Property CMS (Sprints 3, 6, 7).
Handles soft delete, eager relationship loading, audit log versioning, and availability unit tracking.
"""

import json
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload
from fastapi import HTTPException

from app.models.realty import Property, PropertyImage, Review
from app.models.realty_enterprise import (
    PropertyPricing,
    PropertyDocument,
    PropertyVideo,
    AmenityMaster,
    PropertyAmenity,
    PropertyNearbyPlace,
    PropertySEO,
    PropertyShare,
    PropertyAuditLog,
    PropertyUnit,
    PropertyTag,
)
from app.schemas.property_enterprise import (
    CreatePropertyRequest,
    UpdatePropertyRequest,
    PropertyStatusEnum,
)


def get_property_by_id_or_slug(
    db: Session, id_or_slug: Any, include_deleted: bool = False
) -> Optional[Property]:
    """Fetch property by integer id or string slug with all nested enterprise relationships."""
    query = db.query(Property).options(
        selectinload(Property.pricing),
        selectinload(Property.images),
        selectinload(Property.documents),
        selectinload(Property.videos),
        selectinload(Property.property_amenities).selectinload(PropertyAmenity.amenity),
        selectinload(Property.nearby_places),
        selectinload(Property.seo),
        selectinload(Property.share),
        selectinload(Property.units),
        selectinload(Property.tags),
        selectinload(Property.audit_logs),
        selectinload(Property.reviews),
    )
    if not include_deleted:
        query = query.filter(Property.is_deleted == False)

    if isinstance(id_or_slug, int) or (isinstance(id_or_slug, str) and id_or_slug.isdigit()):
        return query.filter(Property.id == int(id_or_slug)).first()
    return query.filter(Property.slug == str(id_or_slug)).first()


def list_properties_enterprise(
    db: Session,
    status: Optional[str] = None,
    visibility: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    locality: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
) -> Tuple[List[Property], int]:
    """List properties with soft-delete filtering and dynamic search filters."""
    query = db.query(Property).filter(Property.is_deleted == False)

    if status:
        query = query.filter(Property.status == status)
    if visibility:
        query = query.filter(Property.visibility == visibility)
    if category:
        query = query.filter(Property.property_category == category)
    if locality:
        query = query.filter(Property.locality.ilike(f"%{locality}%"))
    if tag:
        query = query.join(Property.tags).filter(PropertyTag.tag_name.ilike(f"%{tag}%"))

    total = query.count()
    items = (
        query.options(
            selectinload(Property.pricing),
            selectinload(Property.images),
            selectinload(Property.tags),
            selectinload(Property.units),
        )
        .order_by(desc(Property.id))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return items, total


def create_property_enterprise(
    db: Session,
    data: CreatePropertyRequest,
    current_user_id: int,
    current_user_name: Optional[str] = "Admin",
) -> Property:
    """Create a new property and record the initial version audit log."""
    # Check slug uniqueness
    if data.slug:
        existing = db.query(Property).filter(Property.slug == data.slug, Property.is_deleted == False).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Property with slug '{data.slug}' already exists")

    new_prop = Property(
        property_name=data.property_name,
        slug=data.slug,
        property_code=data.property_code,
        location=data.location,
        city=data.city,
        locality=data.locality,
        phone=data.phone,
        map_link=data.map_link,
        description=data.description,
        property_type=data.property_type,
        listing_type=data.listing_type,
        property_category=data.property_category,
        gender_preference=data.gender_preference,
        available_beds=data.available_beds,
        latitude=data.latitude,
        longitude=data.longitude,
        status=data.status.value,
        visibility=data.visibility.value,
        owner_name=data.owner_name,
        owner_phone=data.owner_phone,
        owner_email=data.owner_email,
        assigned_employee_id=data.assigned_employee_id,
        metadata_json=data.metadata_json or {},
        created_by=str(current_user_id),
        updated_by=str(current_user_id),
    )
    db.add(new_prop)
    db.flush()  # get new_prop.id

    # Add Pricing
    if data.pricing:
        pricing_db = PropertyPricing(
            property_id=new_prop.id,
            starting_price=data.pricing.starting_price,
            max_price=data.pricing.max_price,
            security_deposit=data.pricing.security_deposit,
            maintenance_charges=data.pricing.maintenance_charges,
            electricity_charges=data.pricing.electricity_charges,
            water_charges=data.pricing.water_charges,
            negotiable=data.pricing.negotiable,
            available_offers=data.pricing.available_offers,
            offer_end_date=data.pricing.offer_end_date,
            brokerage=data.pricing.brokerage,
            created_by=str(current_user_id),
        )
        db.add(pricing_db)

    # Add Images
    if data.images:
        from app.models.realty import PropertyImage
        has_primary = any(getattr(i, "is_primary", False) for i in data.images)
        for idx, img in enumerate(data.images):
            db.add(
                PropertyImage(
                    property_id=new_prop.id,
                    image_url=img.image_url or img.public_url or "",
                    is_primary=img.is_primary if has_primary else (idx == 0),
                    sort_order=img.sort_order if img.sort_order is not None else idx,
                    category=img.category or "Bedroom",
                    alt_text=img.alt_text or new_prop.property_name,
                    caption=img.caption,
                    seo_tags=img.seo_tags,
                    created_by=str(current_user_id),
                )
            )

    # Add Documents
    if data.documents:
        for doc in data.documents:
            db.add(
                PropertyDocument(
                    property_id=new_prop.id,
                    document_type=doc.document_type,
                    title=doc.title,
                    document_url=doc.document_url,
                    file_size=doc.file_size,
                    mime_type=doc.mime_type or "application/pdf",
                    created_by=str(current_user_id),
                )
            )

    # Add Videos
    if data.videos:
        for vid in data.videos:
            db.add(
                PropertyVideo(
                    property_id=new_prop.id,
                    title=vid.title,
                    video_url=vid.video_url,
                    thumbnail_url=vid.thumbnail_url,
                    is_short=vid.is_short,
                    sort_order=vid.sort_order,
                    created_by=str(current_user_id),
                )
            )

    # Add Units
    if data.units:
        for u in data.units:
            db.add(
                PropertyUnit(
                    property_id=new_prop.id,
                    unit_code=u.unit_code,
                    unit_type=u.unit_type,
                    status=u.status.value,
                    floor=u.floor,
                    rent_price=u.rent_price,
                    deposit_price=u.deposit_price,
                    occupant_name=u.occupant_name,
                    created_by=str(current_user_id),
                )
            )

    # Add Tags
    if data.tags:
        for t in data.tags:
            db.add(
                PropertyTag(
                    property_id=new_prop.id,
                    tag_name=t.tag_name,
                    tag_category=t.tag_category or "General",
                    created_by=str(current_user_id),
                )
            )

    # Add SEO
    if data.seo:
        db.add(
            PropertySEO(
                property_id=new_prop.id,
                meta_title=data.seo.meta_title,
                meta_description=data.seo.meta_description,
                seo_keywords=data.seo.seo_keywords,
                robots_tag=data.seo.robots_tag or "index, follow",
                twitter_card=data.seo.twitter_card or "summary_large_image",
                og_image=data.seo.og_image,
                canonical_url=data.seo.canonical_url,
                schema_json=data.seo.schema_markup,
                created_by=str(current_user_id),
            )
        )

    # Add Share
    if data.share:
        db.add(
            PropertyShare(
                property_id=new_prop.id,
                short_url=data.share.short_url,
                qr_code_url=data.share.qr_code_url,
                share_title=data.share.share_title,
                share_description=data.share.share_description,
                share_image=data.share.share_image,
                created_by=str(current_user_id),
            )
        )

    # Record Audit Log (Version 1)
    audit = PropertyAuditLog(
        property_id=new_prop.id,
        user_id=current_user_id,
        action="create",
        version_number=1,
        changes_json={
            "action": "create",
            "property_name": data.property_name,
            "status": data.status.value,
            "category": data.property_category,
            "created_by_name": current_user_name,
        },
        created_by=str(current_user_id),
    )
    db.add(audit)

    db.commit()
    db.refresh(new_prop)
    return new_prop


def update_property_enterprise(
    db: Session,
    property_id: int,
    data: UpdatePropertyRequest,
    current_user_id: int,
    current_user_name: Optional[str] = "Admin",
) -> Property:
    """Update existing property, bump version, and store diff in audit log."""
    prop = get_property_by_id_or_slug(db, property_id, include_deleted=False)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Check slug clash if changed
    if data.slug and data.slug != prop.slug:
        existing = db.query(Property).filter(Property.slug == data.slug, Property.id != property_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug '{data.slug}' already in use")

    changes = {}
    for k, v in data.model_dump(exclude_unset=True).items():
        if k in ["pricing", "images", "documents", "videos", "amenities", "nearby_places", "seo", "share", "units", "tags"]:
            continue
        old_val = getattr(prop, k, None)
        if hasattr(v, "value"):
            v = v.value
        if old_val != v:
            changes[k] = {"old": old_val, "new": v}
            setattr(prop, k, v)

    prop.updated_by = str(current_user_id)

    # Update Pricing
    if data.pricing is not None:
        if not prop.pricing:
            prop.pricing = PropertyPricing(property_id=prop.id, created_by=str(current_user_id))
        for pk, pv in data.pricing.model_dump(exclude_unset=True).items():
            setattr(prop.pricing, pk, pv)

    # Update Tags if provided
    if data.tags is not None:
        db.query(PropertyTag).filter(PropertyTag.property_id == prop.id).delete()
        for t in data.tags:
            db.add(
                PropertyTag(
                    property_id=prop.id,
                    tag_name=t.tag_name,
                    tag_category=t.tag_category or "General",
                    created_by=str(current_user_id),
                )
            )

    # Update Units if provided
    if data.units is not None:
        db.query(PropertyUnit).filter(PropertyUnit.property_id == prop.id).delete()
        for u in data.units:
            db.add(
                PropertyUnit(
                    property_id=prop.id,
                    unit_code=u.unit_code,
                    unit_type=u.unit_type,
                    status=u.status.value,
                    floor=u.floor,
                    rent_price=u.rent_price,
                    deposit_price=u.deposit_price,
                    occupant_name=u.occupant_name,
                    created_by=str(current_user_id),
                )
            )

    # Update Images if provided
    if data.images is not None:
        from app.models.realty import PropertyImage
        db.query(PropertyImage).filter(PropertyImage.property_id == prop.id).delete()
        has_primary = any(getattr(i, "is_primary", False) for i in data.images)
        for idx, img in enumerate(data.images):
            db.add(
                PropertyImage(
                    property_id=prop.id,
                    image_url=img.image_url or img.public_url or "",
                    is_primary=img.is_primary if has_primary else (idx == 0),
                    sort_order=img.sort_order if img.sort_order is not None else idx,
                    category=img.category or "Bedroom",
                    alt_text=img.alt_text or prop.property_name,
                    caption=img.caption,
                    seo_tags=img.seo_tags,
                    created_by=str(current_user_id),
                )
            )

    # Compute new version number
    last_log = (
        db.query(PropertyAuditLog)
        .filter(PropertyAuditLog.property_id == prop.id)
        .order_by(desc(PropertyAuditLog.version_number))
        .first()
    )
    new_version = (last_log.version_number + 1) if last_log else 2

    audit = PropertyAuditLog(
        property_id=prop.id,
        user_id=current_user_id,
        action="update",
        version_number=new_version,
        changes_json={"changes": changes, "updated_by_name": current_user_name},
        created_by=str(current_user_id),
    )
    db.add(audit)

    db.commit()
    db.refresh(prop)
    return prop


def transition_property_status(
    db: Session,
    property_id: int,
    new_status: PropertyStatusEnum,
    reason: Optional[str],
    current_user_id: int,
) -> Property:
    """Execute Property Publish Workflow transition (Sprint 6)."""
    prop = get_property_by_id_or_slug(db, property_id, include_deleted=False)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    old_status = prop.status
    prop.status = new_status.value
    prop.updated_by = str(current_user_id)

    last_log = (
        db.query(PropertyAuditLog)
        .filter(PropertyAuditLog.property_id == prop.id)
        .order_by(desc(PropertyAuditLog.version_number))
        .first()
    )
    new_ver = (last_log.version_number + 1) if last_log else 1

    audit = PropertyAuditLog(
        property_id=prop.id,
        user_id=current_user_id,
        action=f"transition_{new_status.value}",
        version_number=new_ver,
        changes_json={"old_status": old_status, "new_status": new_status.value, "reason": reason},
        created_by=str(current_user_id),
    )
    db.add(audit)

    db.commit()
    db.refresh(prop)
    return prop


def soft_delete_property(db: Session, property_id: int, current_user_id: int) -> bool:
    """Soft delete property — data is never permanently erased."""
    prop = get_property_by_id_or_slug(db, property_id, include_deleted=False)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    prop.is_deleted = True
    prop.status = PropertyStatusEnum.archived.value
    prop.updated_by = str(current_user_id)

    audit = PropertyAuditLog(
        property_id=prop.id,
        user_id=current_user_id,
        action="delete",
        version_number=1,
        changes_json={"action": "soft_delete"},
        created_by=str(current_user_id),
    )
    db.add(audit)

    db.commit()
    return True


def restore_property(db: Session, property_id: int, current_user_id: int) -> Property:
    """Restore a soft-deleted property back to draft status."""
    prop = get_property_by_id_or_slug(db, property_id, include_deleted=True)
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    prop.is_deleted = False
    prop.status = PropertyStatusEnum.draft.value
    prop.updated_by = str(current_user_id)

    audit = PropertyAuditLog(
        property_id=prop.id,
        user_id=current_user_id,
        action="restore",
        version_number=1,
        changes_json={"action": "restore_from_trash"},
        created_by=str(current_user_id),
    )
    db.add(audit)

    db.commit()
    db.refresh(prop)
    return prop
