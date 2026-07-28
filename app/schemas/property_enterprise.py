"""
Enterprise Pydantic Schemas for Real Estate Properties (Sprints 3, 5, 6, 7, 10).
Includes strict field validation, workflow statuses, and unified response models.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class PropertyStatusEnum(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    published = "published"
    archived = "archived"


class PropertyVisibilityEnum(str, Enum):
    public = "public"
    private = "private"
    draft = "draft"
    archived = "archived"


class UnitStatusEnum(str, Enum):
    available = "available"
    reserved = "reserved"
    occupied = "occupied"
    maintenance = "maintenance"


# ==================== NESTED SCHEMAS ====================

class PropertyPricingSchema(BaseModel):
    starting_price: Optional[float] = Field(None, ge=0, description="Starting price cannot be negative")
    max_price: Optional[float] = Field(None, ge=0, description="Max price cannot be negative")
    security_deposit: Optional[str] = None
    maintenance_charges: Optional[str] = None
    electricity_charges: Optional[str] = None
    water_charges: Optional[str] = None
    negotiable: bool = False
    available_offers: Optional[str] = None
    offer_end_date: Optional[str] = None
    brokerage: Optional[str] = None

    class Config:
        from_attributes = True


class PropertyDocumentSchema(BaseModel):
    id: Optional[int] = None
    document_type: str = Field(..., description="brochure, pricing, wap, floor_plan, rental_agreement, etc.")
    title: str
    document_url: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = "application/pdf"

    @field_validator("document_url")
    @classmethod
    def validate_document_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Document URL cannot be empty")
        return v.strip()

    class Config:
        from_attributes = True


class PropertyImageSchema(BaseModel):
    id: Optional[Any] = None
    image_url: Optional[str] = None
    public_url: Optional[str] = None
    file_key: Optional[str] = None
    is_primary: bool = False
    category: Optional[str] = "exterior"
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    seo_tags: Optional[str] = None
    sort_order: int = 0

    class Config:
        from_attributes = True
        populate_by_name = True


class PropertyVideoSchema(BaseModel):
    id: Optional[int] = None
    title: str
    video_url: str
    thumbnail_url: Optional[str] = None
    is_short: bool = False
    sort_order: int = 0

    @field_validator("video_url")
    @classmethod
    def validate_youtube_or_video_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Video URL cannot be empty")
        v_clean = v.strip()
        # Basic check for youtube or valid url
        if "youtube.com" not in v_clean and "youtu.be" not in v_clean and not v_clean.startswith("http"):
            raise ValueError("Video URL must be a valid HTTP/YouTube URL")
        return v_clean

    class Config:
        from_attributes = True


class AmenityMasterSchema(BaseModel):
    id: int
    code: str
    name: str
    category: str
    icon_url: Optional[str] = None

    class Config:
        from_attributes = True


class PropertyAmenitySchema(BaseModel):
    id: Optional[int] = None
    amenity_id: Optional[int] = None
    custom_label: Optional[str] = None
    is_custom: bool = False
    amenity: Optional[AmenityMasterSchema] = None

    class Config:
        from_attributes = True


class PropertyNearbyPlaceSchema(BaseModel):
    id: Optional[int] = None
    category: str
    name: str
    distance: str
    travel_time: Optional[str] = None
    google_rating: Optional[str] = None
    map_link: Optional[str] = None
    latitude: Optional[str] = None
    longitude: Optional[str] = None

    class Config:
        from_attributes = True


class PropertySEOSchema(BaseModel):
    meta_title: Optional[str] = None
    meta_description: Optional[str] = None
    seo_keywords: Optional[str] = None
    robots_tag: Optional[str] = "index, follow"
    twitter_card: Optional[str] = "summary_large_image"
    og_image: Optional[str] = None
    canonical_url: Optional[str] = None
    schema_markup: Optional[str] = Field(None, alias="schema_json")

    class Config:
        from_attributes = True
        populate_by_name = True


class PropertyShareSchema(BaseModel):
    short_url: Optional[str] = None
    qr_code_url: Optional[str] = None
    share_title: Optional[str] = None
    share_description: Optional[str] = None
    share_image: Optional[str] = None

    class Config:
        from_attributes = True


class PropertyAuditLogSchema(BaseModel):
    id: int
    property_id: int
    user_id: Optional[int] = None
    action: str
    version_number: int
    changes_json: Optional[Any] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class PropertyUnitSchema(BaseModel):
    id: Optional[int] = None
    unit_code: str
    unit_type: str = "Single"
    status: UnitStatusEnum = UnitStatusEnum.available
    floor: Optional[str] = None
    rent_price: Optional[float] = Field(None, ge=0)
    deposit_price: Optional[float] = Field(None, ge=0)
    occupant_name: Optional[str] = None

    class Config:
        from_attributes = True


class PropertyTagSchema(BaseModel):
    id: Optional[int] = None
    tag_name: str
    tag_category: Optional[str] = "General"

    class Config:
        from_attributes = True


# ==================== REQUEST SCHEMAS ====================

class CreatePropertyRequest(BaseModel):
    property_name: str = Field(..., min_length=2, max_length=150)
    slug: Optional[str] = Field(None, max_length=200)
    property_code: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    phone: Optional[str] = None
    map_link: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = "PG"
    listing_type: str = "rent"
    property_category: Optional[str] = "PG"
    gender_preference: Optional[str] = None
    available_beds: Optional[int] = Field(None, ge=0)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: PropertyStatusEnum = PropertyStatusEnum.draft
    visibility: PropertyVisibilityEnum = PropertyVisibilityEnum.public
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None
    assigned_employee_id: Optional[int] = None

    # Nested sub-resources
    pricing: Optional[PropertyPricingSchema] = None
    images: Optional[List[PropertyImageSchema]] = None
    documents: Optional[List[PropertyDocumentSchema]] = None
    videos: Optional[List[PropertyVideoSchema]] = None
    amenities: Optional[List[PropertyAmenitySchema]] = None
    nearby_places: Optional[List[PropertyNearbyPlaceSchema]] = None
    seo: Optional[PropertySEOSchema] = None
    share: Optional[PropertyShareSchema] = None
    units: Optional[List[PropertyUnitSchema]] = None
    tags: Optional[List[PropertyTagSchema]] = None
    metadata_json: Optional[Dict[str, Any]] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().lower()
            if not re.match(r"^[a-z0-9-_]+$", v_clean):
                raise ValueError("Slug must contain only lowercase letters, numbers, hyphens, and underscores")
            return v_clean
        return v


class UpdatePropertyRequest(BaseModel):
    property_name: Optional[str] = Field(None, min_length=2, max_length=150)
    slug: Optional[str] = Field(None, max_length=200)
    property_code: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    phone: Optional[str] = None
    map_link: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    listing_type: Optional[str] = None
    property_category: Optional[str] = None
    gender_preference: Optional[str] = None
    available_beds: Optional[int] = Field(None, ge=0)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: Optional[PropertyStatusEnum] = None
    visibility: Optional[PropertyVisibilityEnum] = None
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None
    assigned_employee_id: Optional[int] = None

    # Nested sub-resources
    pricing: Optional[PropertyPricingSchema] = None
    images: Optional[List[PropertyImageSchema]] = None
    documents: Optional[List[PropertyDocumentSchema]] = None
    videos: Optional[List[PropertyVideoSchema]] = None
    amenities: Optional[List[PropertyAmenitySchema]] = None
    nearby_places: Optional[List[PropertyNearbyPlaceSchema]] = None
    seo: Optional[PropertySEOSchema] = None
    share: Optional[PropertyShareSchema] = None
    units: Optional[List[PropertyUnitSchema]] = None
    tags: Optional[List[PropertyTagSchema]] = None
    metadata_json: Optional[Dict[str, Any]] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().lower()
            if not re.match(r"^[a-z0-9-_]+$", v_clean):
                raise ValueError("Slug must contain only lowercase letters, numbers, hyphens, and underscores")
            return v_clean
        return v


class PropertyStatusTransitionRequest(BaseModel):
    status: PropertyStatusEnum = Field(..., description="Draft -> Pending Review -> Approved -> Published -> Archived")
    reason: Optional[str] = None


# ==================== UNIFIED RESPONSE SCHEMAS ====================

class PropertyDetailResponse(BaseModel):
    """
    Unified Single-Response Payload for Sprint 10 / GET /api/v1/properties/{id_or_slug}.
    Includes all 11 modules + 3 special features.
    """
    id: int
    property_name: str
    slug: Optional[str] = None
    property_code: Optional[str] = None
    location: Optional[str] = None
    city: Optional[str] = None
    locality: Optional[str] = None
    phone: Optional[str] = None
    map_link: Optional[str] = None
    description: Optional[str] = None
    property_type: Optional[str] = None
    listing_type: str
    property_category: Optional[str] = None
    gender_preference: Optional[str] = None
    available_beds: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    status: str
    visibility: str
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None
    assigned_employee_id: Optional[int] = None
    average_rating: Optional[float] = None
    review_count: int = 0
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None

    # Nested enterprise modules
    pricing: Optional[PropertyPricingSchema] = None
    images: Optional[List[PropertyImageSchema]] = None
    documents: Optional[List[PropertyDocumentSchema]] = None
    videos: Optional[List[PropertyVideoSchema]] = None
    amenities: Optional[List[PropertyAmenitySchema]] = None
    nearby_places: Optional[List[PropertyNearbyPlaceSchema]] = None
    seo: Optional[PropertySEOSchema] = None
    share: Optional[PropertyShareSchema] = None
    units: Optional[List[PropertyUnitSchema]] = None
    tags: Optional[List[PropertyTagSchema]] = None
    audit_logs: Optional[List[PropertyAuditLogSchema]] = None
    metadata_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
