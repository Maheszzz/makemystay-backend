"""Pydantic models shared by admin API routes."""

from typing import List, Optional

from pydantic import BaseModel, Field


class BulkAssign(BaseModel):
    lead_ids: List[int]
    rm_id: int


class ClearWhatsAppFlowSessionRequest(BaseModel):
    phone: str = Field(..., description="Phone number in E.164, e.g. +91XXXXXXXXXX")
    clear_meta_session: bool = Field(
        False,
        description="Also clear Meta flow session key (wa:meta:flow:{phone})",
    )


class AssignLeadRequest(BaseModel):
    rm_id: int


class UpdateLeadStatusRequest(BaseModel):
    status: str


class SetFollowUpRequest(BaseModel):
    follow_up_at: str  # ISO 8601 datetime


class AddNoteRequest(BaseModel):
    note: str


class UpdatePriorityRequest(BaseModel):
    priority: int = Field(..., ge=1, le=3, description="1=Low, 2=Medium, 3=High")


class AutoAssignRequest(BaseModel):
    lead_ids: Optional[List[int]] = None  # None = all unassigned
    rm_ids: Optional[List[int]] = None  # None = all active RMs
    strategy: str = "load_balanced"  # load_balanced | round_robin
