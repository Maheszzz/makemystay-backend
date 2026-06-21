"""Pydantic schemas for WhatsApp widget lead capture."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


class WhatsAppWidgetLeadCreate(BaseModel):
    """
    Input schema for a lead submitted via the website's WhatsApp floating widget.

    Only `name` and `phone` are strictly required — email and other fields
    are collected by the form but treated as optional so the endpoint is
    resilient to partial payloads.
    """

    name: str = Field(..., min_length=1, max_length=200, description="Full name of the visitor")
    phone: str = Field(..., description="10-digit Indian mobile number")
    email: Optional[str] = Field(None, max_length=200, description="Email address")
    preferred_location: Optional[str] = Field(
        None, max_length=200, description="Preferred property location (maps to `location`)"
    )
    property_type: Optional[str] = Field(
        None, max_length=100, description="Property type preference (PG, 1BHK, 2BHK, etc.)"
    )
    message: Optional[str] = Field(
        None, max_length=2000, description="Additional requirements or notes"
    )
    source: str = Field(
        default="Website - WhatsApp Widget",
        max_length=100,
        description="Lead source identifier",
    )

    @field_validator("phone", mode="before")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        """Strip country code prefix and non-digit characters."""
        phone = str(v or "").replace(" ", "").replace("-", "")
        if phone.startswith("+91"):
            phone = phone[3:]
        elif phone.startswith("91") and len(phone) == 12:
            phone = phone[2:]
        if phone.startswith("0"):
            phone = phone[1:]
        if len(phone) < 10:
            raise ValueError("Phone number must be at least 10 digits")
        return phone[:10]


class WhatsAppWidgetLeadResponse(BaseModel):
    """Response returned after successfully saving a widget lead."""

    success: bool = True
    message: str = "Lead captured successfully"
    lead_id: Optional[int] = None
