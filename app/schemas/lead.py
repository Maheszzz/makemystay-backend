"""Pydantic schemas for the unified lead pipeline."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LeadStatus(str, Enum):
    new = "new"
    contacted = "contacted"
    converted = "converted"
    lost = "lost"


class LeadCreate(BaseModel):
    """
    Flexible input schema for incoming leads from any source.

    Only `phone` is mandatory — every lead platform provides a phone number.
    All other fields are optional so the endpoint gracefully accepts whatever
    the source sends.
    """

    name: Optional[str] = Field(None, max_length=200)
    email: Optional[str] = Field(None, max_length=200)
    phone: str = Field(..., pattern=r"^[6-9]\d{9}$")
    project_name: Optional[str] = Field(None, max_length=300)
    city: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    message: Optional[str] = Field(None, max_length=2000)
    requirement: Optional[str] = Field(None, max_length=2000)
    budget: Optional[str] = Field(None, max_length=100)
    property_type: Optional[str] = Field(None, max_length=100)
    lead_date: Optional[int] = None
    external_id: Optional[str] = None
    campaign: Optional[str] = Field(None, max_length=100)
    ad_id: Optional[str] = Field(None, max_length=100)
    property_id: Optional[str] = Field(None, max_length=100)


class LeadResponse(BaseModel):
    """Full lead response with ID, timestamps, and CRM sync status."""

    id: int
    name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    source: str
    city: Optional[str] = None
    location: Optional[str] = None
    project_name: Optional[str] = None
    property_type: Optional[str] = None
    budget: Optional[str] = None
    message: Optional[str] = None
    status: str
    assigned_to: Optional[int] = None
    priority: Optional[int] = None
    zoho_lead_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadWebhookResponse(BaseModel):
    """Response returned by the webhook endpoint."""

    status: str
    message: str
    lead_id: Optional[int] = None
