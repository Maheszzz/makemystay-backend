"""Pydantic schemas for Realty models with validation."""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, EmailStr, field_validator
from enum import Enum


# ==================== ENUMS ====================

class ContactStatus(str, Enum):
    new = "new"
    contacted = "contacted"
    closed = "closed"


class PropertyType(str, Enum):
    PG = "PG"
    ONE_RK = "1RK"
    ONE_BHK = "1BHK"
    TWO_BHK = "2BHK"
    THREE_BHK = "3BHK"
    FOUR_BHK = "4BHK"
    VILLA = "Villa"


class Furnishing(str, Enum):
    fully_furnished = "fully_furnished"
    semi_furnished = "semi_furnished"
    unfurnished = "unfurnished"


class ListingType(str, Enum):
    buy = "buy"
    rent = "rent"


# ==================== CONTACT SCHEMAS ====================

class ContactBase(BaseModel):
    """Base schema for Contact with validation."""
    name_: str = Field(..., min_length=1, max_length=100, alias="name")
    phone: str = Field(..., min_length=10, max_length=15)
    email: EmailStr = Field(..., max_length=150)
    message: str = Field(..., max_length=250)
    status: Optional[ContactStatus] = ContactStatus.new

    model_config = {"populate_by_name": True}


class ContactCreate(ContactBase):
    """Schema for creating a new contact."""
    pass


class ContactUpdate(BaseModel):
    """Schema for updating an existing contact (all fields optional)."""
    name_: Optional[str] = Field(None, min_length=1, max_length=100, alias="name")
    phone: Optional[str] = Field(None, min_length=10, max_length=15)
    email: Optional[EmailStr] = Field(None, max_length=150)
    message: Optional[str] = Field(None, max_length=250)
    status: Optional[ContactStatus] = None

    model_config = {"populate_by_name": True}


class ContactResponse(ContactBase):
    """Schema for contact response with ID and timestamps."""
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


# ==================== PROPERTY IMAGE SCHEMAS ====================

class PropertyImageBase(BaseModel):
    """Base schema for PropertyImage."""
    image_url: str = Field(..., max_length=500)
    is_primary: bool = False
    sort_order: int = Field(default=0, ge=0)


class PropertyImageCreate(PropertyImageBase):
    """Schema for creating a new property image."""
    pass


class PropertyImageUpdate(BaseModel):
    """Schema for updating an existing property image."""
    image_url: Optional[str] = Field(None, max_length=500)
    is_primary: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0)


class PropertyImageResponse(PropertyImageBase):
    """Schema for property image response with ID and timestamps."""
    id: int
    property_id: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator('image_url')
    @classmethod
    def sign_image_url(cls, v: str) -> str:
        from app.utils.cloudfront import get_cloudfront_signed_url
        return get_cloudfront_signed_url(v)


# ==================== REVIEW SCHEMAS ====================

class ReviewBase(BaseModel):
    """Base schema for Review."""
    rating: int = Field(..., ge=1, le=5)
    user_name: str = Field(..., min_length=1, max_length=100)
    comment: Optional[str] = None


class ReviewCreate(ReviewBase):
    """Schema for creating a new review."""
    pass


class ReviewResponse(ReviewBase):
    """Schema for review response with ID and timestamp."""
    id: int
    property_id: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ==================== PROPERTY SCHEMAS ====================

class PropertyBase(BaseModel):
    """Base schema for Property with validation."""
    property_name: str = Field(..., min_length=1, max_length=150)
    location: str = Field(..., min_length=1, max_length=150)
    phone: str = Field(..., min_length=10, max_length=15)
    map_link: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    features: Optional[List[str]] = None
    property_type: str = Field(..., min_length=1, max_length=50)
    furnishing: Optional[Furnishing] = Furnishing.unfurnished
    private_price: Optional[float] = Field(None, ge=0)
    single_price: Optional[float] = Field(None, ge=0)
    double_price: Optional[float] = Field(None, ge=0)
    triple_price: Optional[float] = Field(None, ge=0)
    starting_price: Optional[float] = Field(None, ge=0)
    listing_type: ListingType = ListingType.rent
    is_available: Optional[bool] = True

    @field_validator('property_name', 'location')
    @classmethod
    def validate_non_empty_string(cls, v: str) -> str:
        """Ensure string is not just whitespace."""
        if not v or not v.strip():
            raise ValueError('Must provide a non-empty value')
        return v.strip()

    @field_validator('map_link')
    @classmethod
    def validate_map_link(cls, v: Optional[str]) -> Optional[str]:
        """Validate that map_link is a valid URL if provided."""
        if v is not None and not v.startswith(('http://', 'https://')):
            raise ValueError('map_link must be a valid URL starting with http:// or https://')
        return v


class PropertyCreate(PropertyBase):
    """Schema for creating a new property."""
    pass


class PropertyUpdate(BaseModel):
    """Schema for updating an existing property (all fields optional)."""
    property_name: Optional[str] = Field(None, min_length=1, max_length=150)
    location: Optional[str] = Field(None, min_length=1, max_length=150)
    phone: Optional[str] = Field(None, min_length=10, max_length=15)
    map_link: Optional[str] = Field(None, max_length=500)
    description: Optional[str] = None
    features: Optional[List[str]] = None
    property_type: Optional[str] = Field(None, min_length=1, max_length=50)
    furnishing: Optional[Furnishing] = None
    private_price: Optional[float] = Field(None, ge=0)
    single_price: Optional[float] = Field(None, ge=0)
    double_price: Optional[float] = Field(None, ge=0)
    triple_price: Optional[float] = Field(None, ge=0)
    starting_price: Optional[float] = Field(None, ge=0)
    listing_type: Optional[ListingType] = None
    is_available: Optional[bool] = None

    @field_validator('property_name', 'location')
    @classmethod
    def validate_non_empty_string(cls, v: Optional[str]) -> Optional[str]:
        """Ensure string is not just whitespace if provided."""
        if v is not None:
            if not v or not v.strip():
                raise ValueError('Must provide a non-empty value')
            return v.strip()
        return v

    @field_validator('map_link')
    @classmethod
    def validate_map_link(cls, v: Optional[str]) -> Optional[str]:
        """Validate that map_link is a valid URL if provided."""
        if v is not None and not v.startswith(('http://', 'https://')):
            raise ValueError('map_link must be a valid URL starting with http:// or https://')
        return v


class PropertyResponse(BaseModel):
    """Schema for property response with ID, timestamps, and images."""
    id: int
    property_name: str
    location: str
    phone: Optional[str] = None
    map_link: Optional[str] = None
    description: Optional[str] = None
    features: Optional[List[str]] = []
    property_type: str
    furnishing: Optional[str] = None
    private_price: Optional[float] = None
    single_price: Optional[float] = None
    double_price: Optional[float] = None
    triple_price: Optional[float] = None
    starting_price: Optional[float] = None
    listing_type: str
    is_available: Optional[bool] = None
    created_at: datetime
    updated_at: datetime
    images: List[PropertyImageResponse] = []
    reviews: List[ReviewResponse] = []
    average_rating: Optional[float] = 0.0
    review_count: Optional[int] = 0

    model_config = {"from_attributes": True}

    @field_validator('average_rating', mode='before')
    @classmethod
    def calculate_average_rating(cls, v, info):
        # This is a bit tricky with from_attributes=True
        # We might handle this in the repo or keep it simple
        return v or 0.0

    @field_validator('review_count', mode='before')
    @classmethod
    def calculate_review_count(cls, v, info):
        return v or 0
