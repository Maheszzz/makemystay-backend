from sqlalchemy import (
    BigInteger,
    DECIMAL,
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.configs.db_config import MySQLBase


class Contact(MySQLBase):
    """Model for contacts table"""

    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name_ = Column("name_", String(100), nullable=False)  # Column is 'name_' in DB
    phone = Column(String(15), nullable=False)
    email = Column(String(150), nullable=False)
    message = Column(String(250), nullable=False)
    location = Column(String(100), nullable=True)
    property_type = Column(String(50), nullable=True)
    source = Column(String(100), nullable=True, default="Website")
    status = Column(
        Enum("new", "contacted", "closed", name="contact_status"),
        default="new",
        nullable=True,
    )
    is_ai_called = Column(Boolean, default=False)
    call_status = Column(String(50), nullable=True)
    interested = Column(Boolean, nullable=True)
    budget = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )
    
    # Relationships
    retell_calls = relationship("RetellCall", back_populates="contact")

class Property(MySQLBase):
    """Model for properties table"""

    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_name = Column(String(150), nullable=False, index=True)
    location = Column(String(150), nullable=True, index=True)
    city = Column(String(50), nullable=True, index=True)
    phone = Column(String(15), nullable=True)
    map_link = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    features = Column(JSON, nullable=True)
    property_type = Column(String(50), nullable=True)
    furnishing = Column(
        Enum(
            "fully_furnished", "semi_furnished", "unfurnished", name="furnishing_enum"
        ),
        nullable=True,
    )
    private_price = Column(DECIMAL(10, 2), nullable=True)  # For 1BHK, 1RK etc
    single_price = Column(DECIMAL(10, 2), nullable=True)
    double_price = Column(DECIMAL(10, 2), nullable=True)
    triple_price = Column(DECIMAL(10, 2), nullable=True)
    starting_price = Column(DECIMAL(10, 2), nullable=True)
    listing_type = Column(Enum("buy", "rent", name="listing_type_enum"), nullable=False)
    is_available = Column(Boolean, default=True, nullable=True)
    slug = Column(String(200), unique=True, index=True, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    # Denormalized from reviews — updated on review write; used for list sort + slim list payload.
    average_rating = Column("avg_rating", DECIMAL(4, 2), nullable=True)
    review_count = Column(Integer, nullable=False, server_default="0", default=0)
    property_code = Column(String(50), unique=True, index=True, nullable=True)
    gender_preference = Column(String(50), nullable=True)
    property_category = Column(String(100), nullable=True)
    locality = Column(String(150), nullable=True, index=True)
    latitude = Column(DECIMAL(10, 8), nullable=True)
    longitude = Column(DECIMAL(11, 8), nullable=True)
    available_beds = Column(Integer, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    last_verified_at = Column(DateTime, nullable=True)
    last_booked_at = Column(DateTime, nullable=True)
    last_review_at = Column(DateTime, nullable=True)
    status = Column(
        String(32), default="draft", nullable=False, index=True, doc="draft, pending_review, approved, published, archived"
    )
    visibility = Column(String(32), default="public", nullable=False, doc="public, private, draft, archived")
    owner_name = Column(String(150), nullable=True)
    owner_phone = Column(String(32), nullable=True)
    owner_email = Column(String(150), nullable=True)
    assigned_employee_id = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)

    # Relationships
    images = relationship(
        "PropertyImage", back_populates="property", cascade="all, delete-orphan"
    )
    reviews = relationship(
        "Review", back_populates="property", cascade="all, delete-orphan"
    )
    pricing = relationship(
        "PropertyPricing", back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    documents = relationship(
        "PropertyDocument", back_populates="property", cascade="all, delete-orphan"
    )
    videos = relationship(
        "PropertyVideo", back_populates="property", cascade="all, delete-orphan"
    )
    property_amenities = relationship(
        "PropertyAmenity", back_populates="property", cascade="all, delete-orphan"
    )
    nearby_places = relationship(
        "PropertyNearbyPlace", back_populates="property", cascade="all, delete-orphan"
    )
    seo = relationship(
        "PropertySEO", back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    share = relationship(
        "PropertyShare", back_populates="property", uselist=False, cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "PropertyAuditLog", back_populates="property", cascade="all, delete-orphan"
    )
    units = relationship(
        "PropertyUnit", back_populates="property", cascade="all, delete-orphan"
    )
    tags = relationship(
        "PropertyTag", back_populates="property", cascade="all, delete-orphan"
    )
    leads_history = relationship(
        "PropertyLead", back_populates="property", cascade="all, delete-orphan"
    )


class PropertyImage(MySQLBase):
    """Model for property_images table"""

    __tablename__ = "property_images"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False
    )
    image_url = Column(String(500), nullable=False)
    content_type = Column(String(80), nullable=False, default="image/jpeg")
    mime_validated = Column(Boolean, nullable=False, default=True)
    file_size = Column(BigInteger, nullable=True)
    is_primary = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    category = Column(String(80), default="Bedroom", nullable=True)
    alt_text = Column(String(200), nullable=True)
    caption = Column(String(250), nullable=True)
    seo_tags = Column(String(250), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)

    # Relationship to property
    property = relationship("Property", back_populates="images")


class Review(MySQLBase):
    """Model for reviews table"""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    property_id = Column(
        Integer,
        ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False,
    )
    rating = Column(Integer, nullable=False)  # 1-5 overall
    cleanliness_rating = Column(Integer, nullable=True)
    wifi_rating = Column(Integer, nullable=True)
    food_rating = Column(Integer, nullable=True)
    safety_rating = Column(Integer, nullable=True)
    user_name = Column(String(100), nullable=False)
    property_name = Column(String(150), nullable=True)
    comment = Column(Text, nullable=True)
    owner_response = Column(Text, nullable=True)
    review_images = Column(JSON, nullable=True)
    verified_stay = Column(Boolean, nullable=False, default=False, server_default="0")
    status = Column(String(20), nullable=False, default="pending", server_default="pending")
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=True
    )
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)

    # Relationship to property
    property = relationship("Property", back_populates="reviews")
