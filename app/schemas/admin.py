"""Pydantic schemas for Administrative operations."""

from typing import List
from pydantic import BaseModel
from app.schemas.lead import LeadResponse
from app.schemas.realty import PropertyResponse

class GlobalSearchResponse(BaseModel):
    """Schema for global search results."""
    properties: List[PropertyResponse]
    leads: List[LeadResponse]

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
