"""Pydantic schemas for the unified lead pipeline."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


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

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone_input(cls, v: str) -> str:
        if not v:
            return ""
        phone = str(v).replace(" ", "").replace("-", "")
        if phone.startswith("+91"):
            phone = phone[3:]
        if phone.startswith("0"):
            phone = phone[1:]
        return phone
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


class LeadEmployeeResponse(BaseModel):
    id: int
    employee_id: str
    name: str

    class Config:
        from_attributes = True


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
    notes: Optional[str] = None
    status: str
    lead_stage: str = "new"
    crm_status: str = "pending"
    assigned_to: Optional[int] = None
    assigned_employee_id: Optional[int] = None
    assigned_employee: Optional[LeadEmployeeResponse] = None
    priority: Optional[int] = None
    follow_up_at: Optional[datetime] = None
    zoho_lead_id: Optional[str] = None
    zoho_synced: bool = False
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadWebhookResponse(BaseModel):
    """Response returned by the webhook endpoint."""

    status: str
    message: str
    lead_id: Optional[int] = None
