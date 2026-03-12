"""Pydantic schemas for Administrative operations."""

from typing import List, Optional
from pydantic import BaseModel
from app.schemas.lead import LeadResponse

class DashboardStats(BaseModel):
    """Schema for high-level dashboard metrics."""
    total_leads: int
    total_properties: int
    total_contacts: int
    total_ai_calls: int
    active_listings: int

class AdminLeadResponse(LeadResponse):
    """Extended lead response for admin view if needed."""
    pass
