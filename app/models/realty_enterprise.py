"""
Enterprise Real Estate Models for MakeMyStay CMS.
Supports Sprints 1 to 10 + 3 Special Features: Version History (Audit Logs), Unit Availability, and Tags.
All models implement mandatory soft delete (`is_deleted`) and audit timestamps (`created_by`, `updated_by`).
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    DECIMAL,
    Enum,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.configs.db_config import MySQLBase


class PropertyPricing(MySQLBase):
    """Extended pricing matrix for properties (Sprint 1)."""

    __tablename__ = "property_pricing"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    starting_price = Column(DECIMAL(10, 2), nullable=True)
    max_price = Column(DECIMAL(10, 2), nullable=True)
    security_deposit = Column(String(100), nullable=True)
    maintenance_charges = Column(String(100), nullable=True)
    electricity_charges = Column(String(100), nullable=True)
    water_charges = Column(String(100), nullable=True)
    negotiable = Column(Boolean, default=False, nullable=False)
    available_offers = Column(Text, nullable=True)
    offer_end_date = Column(String(32), nullable=True)
    brokerage = Column(String(100), nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="pricing")


class PropertyDocument(MySQLBase):
    """Enterprise PDF & Sales Kit documents (Sprint 1 & 3)."""

    __tablename__ = "property_documents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type = Column(
        String(50),
        nullable=False,
        index=True,
        doc="brochure, pricing, wap, floor_plan, rental_agreement, interior_catalog, furniture_list, legal_documents, etc.",
    )
    title = Column(String(200), nullable=False)
    document_url = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String(80), default="application/pdf", nullable=False)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="documents")


class PropertyVideo(MySQLBase):
    """Property Video Tours & Shorts (Sprint 1 & 3)."""

    __tablename__ = "property_videos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title = Column(String(200), nullable=False)
    video_url = Column(String(500), nullable=False)
    thumbnail_url = Column(String(500), nullable=True)
    is_short = Column(Boolean, default=False, nullable=False, doc="True for vertical 9:16 Shorts/Reels")
    sort_order = Column(Integer, default=0, nullable=False)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="videos")


class AmenityMaster(MySQLBase):
    """Master table for amenities with custom icon and category support (Sprint 1 & 3)."""

    __tablename__ = "amenity_master"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(150), nullable=False)
    category = Column(
        String(80),
        nullable=False,
        default="Room",
        doc="Room, Building, Kitchen & Appliances, Safety & Security, Luxury & Leisure",
    )
    icon_url = Column(String(500), nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)


class PropertyAmenity(MySQLBase):
    """Association table connecting properties to amenities (Sprint 1 & 3)."""

    __tablename__ = "property_amenities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amenity_id = Column(
        Integer, ForeignKey("amenity_master.id", ondelete="CASCADE"), nullable=True, index=True
    )
    custom_label = Column(String(150), nullable=True)
    is_custom = Column(Boolean, default=False, nullable=False)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="property_amenities")
    amenity = relationship("AmenityMaster")


class PropertyNearbyPlace(MySQLBase):
    """Geo-connected neighborhood landmarks and travel times (Sprint 1 & 3)."""

    __tablename__ = "property_nearby_places"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = Column(
        String(80),
        nullable=False,
        default="Metro",
        doc="Metro, Hospital, School, Mall, Bus Stop, Tech Park, Airport",
    )
    name = Column(String(150), nullable=False)
    distance = Column(String(64), nullable=False)
    travel_time = Column(String(64), nullable=True)
    google_rating = Column(String(16), nullable=True)
    map_link = Column(String(500), nullable=True)
    latitude = Column(String(32), nullable=True)
    longitude = Column(String(32), nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="nearby_places")


class PropertySEO(MySQLBase):
    """Enterprise SEO & Schema.org JSON-LD Metadata (Sprint 1 & 3)."""

    __tablename__ = "property_seo"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    meta_title = Column(String(200), nullable=True)
    meta_description = Column(Text, nullable=True)
    seo_keywords = Column(Text, nullable=True)
    robots_tag = Column(String(64), default="index, follow", nullable=False)
    twitter_card = Column(String(64), default="summary_large_image", nullable=False)
    og_image = Column(String(500), nullable=True)
    canonical_url = Column(String(500), nullable=True)
    schema_json = Column(Text, nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="seo")


class PropertyShare(MySQLBase):
    """Viral social sharing, QR codes, and short URLs (Sprint 1 & 3)."""

    __tablename__ = "property_share"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    short_url = Column(String(200), nullable=True)
    qr_code_url = Column(String(500), nullable=True)
    share_title = Column(String(200), nullable=True)
    share_description = Column(Text, nullable=True)
    share_image = Column(String(500), nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="share")


# ==============================================================================
# SPECIAL FEATURE #1: Version History & Audit Logs
# ==============================================================================
class PropertyAuditLog(MySQLBase):
    """
    Version history audit log recording timestamped diffs and JSON snapshots
    for every modification to a property (Special Feature #1).
    """

    __tablename__ = "property_audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, nullable=True, index=True)
    action = Column(
        String(64),
        nullable=False,
        doc="create, update, publish, archive, restore, edit_pricing, edit_media",
    )
    version_number = Column(Integer, nullable=False, default=1)
    changes_json = Column(JSON, nullable=True, doc="Old vs new diff and snapshot of property data")

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="audit_logs")


# ==============================================================================
# SPECIAL FEATURE #2: Availability & Unit Management
# ==============================================================================
class PropertyUnit(MySQLBase):
    """
    Unit-level availability and occupancy tracking (Special Feature #2).
    Tracks room/unit availability, reserved rooms, occupied rooms, maintenance, etc.
    """

    __tablename__ = "property_units"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    unit_code = Column(String(64), nullable=False, index=True, doc="e.g. Room 101, Bed A, Unit 4B")
    unit_type = Column(
        String(64),
        nullable=False,
        default="Single",
        doc="Single, Double, Triple, Studio, 1BHK, 2BHK",
    )
    status = Column(
        Enum("available", "reserved", "occupied", "maintenance", name="unit_status_enum"),
        default="available",
        nullable=False,
        index=True,
    )
    floor = Column(String(32), nullable=True)
    rent_price = Column(DECIMAL(10, 2), nullable=True)
    deposit_price = Column(DECIMAL(10, 2), nullable=True)
    occupant_name = Column(String(150), nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="units")


# ==============================================================================
# SPECIAL FEATURE #3: Property Tags & Filters
# ==============================================================================
class PropertyTag(MySQLBase):
    """
    Flexible tags and filters for search and recommendation (Special Feature #3).
    e.g., Near Metro, Pet Friendly, Students, Family, Luxury, New Launch.
    """

    __tablename__ = "property_tags"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tag_name = Column(String(100), nullable=False, index=True)
    tag_category = Column(String(80), nullable=True, default="General")

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="tags")


# ==============================================================================
# SPRINT 8 & 9: Analytics & Lead Capture Models
# ==============================================================================
class PropertyView(MySQLBase):
    """Track property views and time on page (Sprint 8)."""

    __tablename__ = "property_views"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    viewer_ip = Column(String(64), nullable=True)
    user_id = Column(Integer, nullable=True, index=True)
    time_on_page_seconds = Column(Integer, default=0, nullable=False)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)


class PropertyDownload(MySQLBase):
    """
    Track brochure, pricing, WAP downloads and lead capture fields (Sprint 8 & 9).
    Before downloading premium documents, user must provide Name, Phone, Email, Company, Purpose.
    """

    __tablename__ = "property_downloads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_type = Column(String(64), nullable=False, index=True)
    user_name = Column(String(150), nullable=False)
    user_phone = Column(String(32), nullable=False)
    user_email = Column(String(150), nullable=False)
    user_company = Column(String(150), nullable=True)
    purpose = Column(String(150), nullable=True)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)


class PropertyLead(MySQLBase):
    """
    Auto-generated CRM lead connection when a user downloads a brochure/pricing/WAP
    or books a visit (Sprint 9).
    """

    __tablename__ = "property_leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lead_id = Column(
        Integer, ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source = Column(
        String(64),
        nullable=False,
        doc="brochure_download, pricing_download, wap_download, book_visit, whatsapp_click, call_click",
    )
    assigned_employee_id = Column(
        Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status = Column(String(64), default="New", nullable=False)

    # Soft Delete & Audit
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    property = relationship("Property", back_populates="leads_history")
