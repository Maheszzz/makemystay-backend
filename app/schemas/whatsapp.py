from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WhatsAppLeadPayload(BaseModel):
    phone: str = Field(..., description="Recipient phone in E.164 format, e.g. +91XXXXXXXXXX")
    name: Optional[str] = Field(None, description="Template variable 1")
    city: Optional[str] = Field(None, description="Template variable 2")
    budget: Optional[str] = Field(None, description="Template variable 3")
    lead_id: Optional[int] = Field(None, description="Optional lead id for event logging")
    variables: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional raw Content API variables map, overrides name/city/budget when provided",
    )


class WhatsAppBulkSendRequest(BaseModel):
    leads: List[WhatsAppLeadPayload]
    content_sid: Optional[str] = Field(
        None, description="Twilio Content SID (template SID). Defaults to TWILIO_WHATSAPP_TEMPLATE_SID."
    )
    dry_run: bool = Field(False, description="If true, validates and returns recipients without sending.")
    per_message_delay_ms: int = Field(
        500, ge=0, le=5000, description="Delay between messages for rate limiting"
    )


class WhatsAppBulkSendResponse(BaseModel):
    queued: bool
    job_id: Optional[str] = None
    total: int
    dry_run: bool

