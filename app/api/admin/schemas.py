from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class BulkAssign(BaseModel):
    lead_ids: List[int]
    rm_id: int


class BulkAssignToEmployeeRequest(BaseModel):
    """POST /leads/assign/bulk — assign many leads to one CRM employee (`employees.id`)."""

    lead_ids: List[int]
    employee_id: int


class ClearWhatsAppFlowSessionRequest(BaseModel):
    phone: str = Field(..., description="Phone number in E.164, e.g. +91XXXXXXXXXX")
    clear_meta_session: bool = Field(
        False,
        description="Also clear Meta flow session key (wa:meta:flow:{phone})",
    )


class AssignLeadToRmRequest(BaseModel):
    """Legacy: assign lead to auth User (RM) via PUT /leads/{lead_id}/assign."""

    rm_id: int


class AssignLeadRequest(BaseModel):
    """POST /leads/assign — `employee_id` is the primary key of `employees` (not the EMP001 code)."""

    lead_id: int
    employee_id: int


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


class EmployeeCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: str
    role: str = "RM"


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    user_id: Optional[int] = None


class EmployeeResponse(BaseModel):
    id: int
    employee_id: str
    name: str
    email: Optional[str] = None
    phone: str
    role: str
    status: str
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LeadCsvImportResponse(BaseModel):
    """POST /admin/leads/import-csv — counts from ``csv_lead_import.run_csv_import``."""

    import_id: Optional[int] = None
    imported: int
    duplicates: int
    skipped_no_phone: int
    skipped_empty: int = 0
    errors: int
    row_count: int
    error_samples: List[str] = Field(default_factory=list)
    status: Optional[str] = "completed"


class CsvImportResponse(BaseModel):
    id: int
    file_name: str
    source: str
    total_rows: int
    imported: int
    duplicates: int
    failed: int
    skipped_no_phone: int
    status: str
    created_at: datetime
    created_by_name: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    rows_per_second: Optional[float] = None
    failure_rate: Optional[float] = None
    success_rate: Optional[float] = None
    avg_row_latency_ms: Optional[float] = None

    class Config:
        from_attributes = True


class CsvImportRetryQueuedResponse(BaseModel):
    import_id: int
    status: str = "queued"
