"""
CRM / leads admin: metadata, RMs, lead CRUD, assignments, timeline, funnel, workload.
"""

import asyncio
import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from loguru import logger
from sqlalchemy import case, func, or_
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session, joinedload

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.log_dedupe import should_log_once
from app.core.rate_limit import limiter
from app.core.redis import lead_queue
from app.core.lead_pipeline import VALID_LEAD_STAGES
from app.core.lead_schema import (
    VALID_LEAD_STATUSES,
    build_lead_metadata_payload,
    LEAD_STATUS_LABELS,
    LEAD_STATUS_ORDER,
    LEAD_STATUS_TONES,
    PRIORITY_LEVELS,
)
from app.models.assignment_batch import AssignmentBatch
from app.models.csv_import import CsvImport
from app.models.employee import Employee
from app.models.lead import Lead
from app.models.lead_event import LeadEvent
from app.models.retell_call import RetellCall
from app.models.realty import Property
from app.models.lead_activity import LeadActivity
from app.models.lead_assignment import LeadAssignment
from app.models.sync_metadata import SyncMetadata
from app.models.user import User

from app.api.admin.schemas import (
    AddNoteRequest,
    AssignLeadRequest,
    AssignLeadToRmRequest,
    AutoAssignRequest,
    BulkAssign,
    BulkAssignToEmployeeRequest,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    SetFollowUpRequest,
    UpdateLeadMessageRequest,
    UpdateLeadStageRequest,
    UpdateLeadStatusRequest,
    UpdatePriorityRequest,
)
from app.utils.employee_utils import generate_next_employee_id

router = APIRouter()


def _lead_to_api_dict(lead: Lead, columns) -> dict:
    """Serialize Lead ORM row for JSON (includes nested assigned_employee when loaded)."""
    out: dict = {}
    for col in columns:
        v = getattr(lead, col)
        if v is None:
            out[col] = None
        elif hasattr(v, "isoformat"):
            out[col] = v.isoformat()
        elif hasattr(v, "value"):  # Enum
            out[col] = v.value
        else:
            out[col] = v
    ae = lead.assigned_employee
    if ae is not None:
        out["assigned_employee"] = {
            "id": ae.id,
            "employee_id": ae.employee_id,
            "name": ae.name,
        }
    else:
        out["assigned_employee"] = None
    return out


def _month_datetime_bounds(d: date) -> Tuple[datetime, datetime]:
    """Start (inclusive) and end (exclusive) of the calendar month containing `d`."""
    start = datetime(d.year, d.month, 1)
    if d.month == 12:
        end = datetime(d.year + 1, 1, 1)
    else:
        end = datetime(d.year, d.month + 1, 1)
    return start, end


def _first_day_prev_month(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


@router.get(
    "/lead-metadata",
    summary="Lead statuses, priorities, pipeline stages, contact statuses (single source for admin UI)",
)
def get_lead_metadata(user=Depends(security.get_current_user)):
    """Returns labels and options derived from the Lead model / DB enum — no hardcoding in the frontend."""
    if user.role not in ["admin", "RM", "employee"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return build_lead_metadata_payload()


@router.get("/stats", summary="Get lead ingestion statistics")
async def get_stats(db: Session = Depends(get_mysql_db)):
    """Provides visibility into lead ingestion health and queue status."""
    try:
        today = func.date(Lead.created_at) == func.current_date()
        total_today = db.query(Lead).filter(today).count()

        status_counts = db.query(Lead.crm_status, func.count(Lead.id)).filter(today).group_by(Lead.crm_status).all()

        sync_meta = db.query(SyncMetadata).all()
        sync_info = [
            {
                "source": s.source,
                "last_sync": s.last_sync_at,
                "status": s.status,
                "leads_fetched": s.leads_fetched,
                "last_error": s.last_error,
            }
            for s in sync_meta
        ]

        queue_size = len(lead_queue.job_ids) if lead_queue else 0

        return {
            "today": {"total": total_today, "breakdown": dict(status_counts)},
            "sync_status": sync_info,
            "queue_backlog": queue_size,
        }
    except Exception as e:
        logger.error(f"Failed to fetch admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")


@router.get("/crm/sync-status", summary="Get Zoho CRM synchronization progress")
async def get_crm_sync_status(
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user)
):
    """Provides real-time visibility into the Zoho CRM synchronization progress."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not allowed")

    try:
        total = db.query(Lead).filter(Lead.is_deleted.is_(False)).count()
        synced = db.query(Lead).filter(Lead.is_deleted.is_(False), Lead.zoho_synced.is_(True)).count()
        remaining = total - synced
        
        # Calculate percentage
        percent = (synced / total * 100) if total > 0 else 100
        
        # Also check failures
        failed = db.query(Lead).filter(Lead.crm_status == "failed").count()

        return {
            "total_leads": total,
            "synced_leads": synced,
            "remaining": remaining,
            "failed_leads": failed,
            "sync_percentage": round(percent, 2),
            "status": "in_progress" if remaining > 0 else "complete"
        }
    except Exception as e:
        logger.error(f"Failed to fetch CRM sync status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sync status")


@router.get("/analytics", summary="Get simple analytics metrics")
@limiter.limit("10/minute")
async def analytics(request: Request, db: Session = Depends(get_mysql_db)):
    """High-level CRM + inventory metrics, including month-over-month new listings and leads."""

    def _fetch_data():
        total_leads = db.query(Lead).count()
        today = func.date(Lead.created_at) == func.current_date()
        today_leads = db.query(Lead).filter(today).count()
        failed = db.query(Lead).filter(Lead.crm_status == "failed").count()

        not_deleted = Property.is_deleted == False  # noqa: E712
        total_properties = db.query(Property).filter(not_deleted).count()
        active_properties = (
            db.query(Property).filter(not_deleted, Property.is_available == True).count()  # noqa: E712
        )

        today_d = date.today()
        this_start, this_end = _month_datetime_bounds(today_d)
        prev_anchor = _first_day_prev_month(today_d)
        prev_start, prev_end = _month_datetime_bounds(prev_anchor)

        properties_added_this_month = (
            db.query(Property)
            .filter(
                not_deleted,
                Property.created_at.isnot(None),
                Property.created_at >= this_start,
                Property.created_at < this_end,
            )
            .count()
        )
        properties_added_last_month = (
            db.query(Property)
            .filter(
                not_deleted,
                Property.created_at.isnot(None),
                Property.created_at >= prev_start,
                Property.created_at < prev_end,
            )
            .count()
        )

        leads_this_month = (
            db.query(Lead)
            .filter(
                Lead.created_at.isnot(None),
                Lead.created_at >= this_start,
                Lead.created_at < this_end,
            )
            .count()
        )
        leads_last_month = (
            db.query(Lead)
            .filter(
                Lead.created_at.isnot(None),
                Lead.created_at >= prev_start,
                Lead.created_at < prev_end,
            )
            .count()
        )

        failed_lead_ids = [
            row[0]
            for row in db.query(Lead.id)
            .filter(Lead.crm_status == "failed")
            .order_by(Lead.id.asc())
            .limit(50)
            .all()
        ]

        # Rows that received a Zoho Lead ID after sync (closest to “exists in Zoho org”).
        # Zoho Home “My Leads” is owner-scoped and will usually differ from both totals.
        leads_linked_zoho = (
            db.query(Lead)
            .filter(Lead.zoho_lead_id.isnot(None), Lead.zoho_lead_id != "")
            .count()
        )

        src_rows = db.query(Lead.source, func.count(Lead.id)).group_by(Lead.source).all()
        leads_by_source = {str(s[0]): s[1] for s in src_rows}

        st_rows = db.query(Lead.lead_stage, func.count(Lead.id)).group_by(Lead.lead_stage).all()
        leads_by_stage = {str(s[0]): s[1] for s in st_rows}

        crm_ok = db.query(Lead).filter(Lead.crm_status == "success").count()
        crm_sync_success_rate = (crm_ok / total_leads) if total_leads else None

        crm_bad = (
            db.query(Lead)
            .filter(Lead.crm_status.in_(["failed", "permanently_failed"]))
            .count()
        )
        crm_sync_failed_rate = (crm_bad / total_leads) if total_leads else None

        duplicate_reentry_leads = db.query(Lead).filter(Lead.reentry_count > 0).count()
        duplicate_reentry_rate = (duplicate_reentry_leads / total_leads) if total_leads else None

        reentry_events_total = int(
            db.query(func.coalesce(func.sum(Lead.reentry_count), 0)).scalar() or 0
        )

        cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
        csv_avg = (
            db.query(func.avg(CsvImport.success_rate))
            .filter(CsvImport.created_at >= cutoff_30d, CsvImport.success_rate.isnot(None))
            .scalar()
        )

        return {
            "total_leads": total_leads,
            "leads_linked_zoho": leads_linked_zoho,
            "today_leads": today_leads,
            "failed": failed,
            "failed_lead_ids": failed_lead_ids,
            "total_properties": total_properties,
            "active_properties": active_properties,
            "properties_added_this_month": properties_added_this_month,
            "properties_added_last_month": properties_added_last_month,
            "leads_this_month": leads_this_month,
            "leads_last_month": leads_last_month,
            "leads_by_source": leads_by_source,
            "leads_by_stage": leads_by_stage,
            "crm_sync_success_rate": crm_sync_success_rate,
            "crm_sync_failed_rate": crm_sync_failed_rate,
            "duplicate_reentry_leads": duplicate_reentry_leads,
            "duplicate_reentry_rate": duplicate_reentry_rate,
            "reentry_events_total": reentry_events_total,
            "csv_import_avg_success_rate_30d": float(csv_avg) if csv_avg is not None else None,
        }

    try:
        data = await asyncio.wait_for(asyncio.to_thread(_fetch_data), timeout=10.0)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch analytics (returned safe default): {e}")
        return {
            "total_leads": 0,
            "leads_linked_zoho": 0,
            "today_leads": 0,
            "failed": 0,
            "failed_lead_ids": [],
            "total_properties": 0,
            "active_properties": 0,
            "properties_added_this_month": 0,
            "properties_added_last_month": 0,
            "leads_this_month": 0,
            "leads_last_month": 0,
            "leads_by_source": {},
            "leads_by_stage": {},
            "crm_sync_success_rate": 0,
            "crm_sync_failed_rate": 1.0,
            "duplicate_reentry_leads": 0,
            "reentry_events_total": 0,
            "csv_import_avg_success_rate_30d": 0.0,
        }


@router.get("/analytics/growth", summary="Monthly properties and leads growth for charts")
@limiter.limit("20/minute")
async def analytics_growth(request: Request, db: Session = Depends(get_mysql_db)):
    """Returns month-by-month totals for properties added and leads created — last 12 months."""
    from calendar import month_abbr

    def _fetch():
        today_d = date.today()
        months = []
        for i in range(11, -1, -1):
            # walk back i full months from current
            month_offset = today_d.month - 1 - i
            year_offset = today_d.year + (month_offset // 12)
            mo = (month_offset % 12) + 1
            start, end = _month_datetime_bounds(date(year_offset, mo, 1))

            props = (
                db.query(Property)
                .filter(
                    Property.is_deleted == False,  # noqa: E712
                    Property.created_at.isnot(None),
                    Property.created_at >= start,
                    Property.created_at < end,
                )
                .count()
            )
            leads = (
                db.query(Lead)
                .filter(
                    Lead.created_at.isnot(None),
                    Lead.created_at >= start,
                    Lead.created_at < end,
                )
                .count()
            )
            months.append({
                "name": f"{month_abbr[mo]} '{str(year_offset)[2:]}",
                "month": mo,
                "year": year_offset,
                "properties": props,
                "leads": leads,
            })
        return months

    try:
        # Increase timeout to 10s for potentially slow DB queries on large datasets
        data = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=10.0)
        return data
    except Exception as e:
        logger.error(f"analytics/growth error (returned safe []): {e}")
        # Return empty list to avoid breaking UI charts with 500 error
        return []


@router.get("/users/rms", summary="Get all active Relationship Managers")
def get_rms(db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    """Fetch active users with the RM or employee role for the assignment dropdown."""
    if user.role not in ["admin", "employee"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return db.query(User).filter(User.role == "employee").all()


@router.post("/employees", response_model=EmployeeResponse, summary="Create a new CRM employee")
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create employees")

    # Check for duplicate email if provided
    if data.email:
        existing = db.query(Employee).filter(Employee.email == data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Employee with this email already exists")

    new_emp = Employee(
        employee_id=generate_next_employee_id(db),
        name=data.name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        status="active",
    )
    db.add(new_emp)
    db.commit()
    db.refresh(new_emp)
    return new_emp


@router.get("/employees", response_model=List[EmployeeResponse], summary="List CRM employees")
def list_employees(
    for_hub: bool = Query(
        False,
        description="Admin only: return all employees (any status/role), newest first — for Employee Hub.",
    ),
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    if user.role not in ["admin", "employee"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    if for_hub:
        if user.role != "admin":
            raise HTTPException(status_code=403, detail="Only admins can list all employees")
        return db.query(Employee).order_by(Employee.id.desc()).all()
    # Lead-assignment dropdown: any active employee (role is free text — e.g. "Senior RM", not exact "RM").
    return (
        db.query(Employee)
        .filter(Employee.status == "active")
        .order_by(Employee.name.asc())
        .all()
    )


@router.put("/employees/{emp_id}", response_model=EmployeeResponse, summary="Update an employee")
def update_employee(
    emp_id: int,
    data: EmployeeUpdate,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update employees")
    
    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(emp, key, value)
    
    db.commit()
    db.refresh(emp)
    return emp


@router.post("/leads/assign", summary="Manually assign a lead to a CRM employee")
def assign_lead_to_employee(
    data: AssignLeadRequest,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can assign leads")

    lead = db.query(Lead).filter(Lead.id == data.lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    emp = (
        db.query(Employee)
        .filter(
            Employee.id == data.employee_id,
            Employee.status == "active",
        )
        .first()
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Active employee not found")

    lead.assigned_employee_id = emp.id
    if emp.user_id is not None:
        lead.owner_id = emp.user_id

    label = f"{emp.name} ({emp.employee_id})"
    _log_activity(db, lead.id, "ASSIGNED", f"Assigned to employee {label}", user.id)

    db.commit()
    db.refresh(lead)

    # Trigger Zoho CRM sync to update Owner
    try:
        from app.tasks.lead_tasks import sync_lead_to_zoho_task
        sync_lead_to_zoho_task.delay(lead.id)
    except Exception as e:
        logger.error(f"Failed to trigger Zoho sync after assignment: {e}")

    return {
        "message": "Assigned successfully",
        "lead_id": lead.id,
        "assigned_employee_id": emp.id,
        "assigned_employee": {"id": emp.id, "employee_id": emp.employee_id, "name": emp.name},
        "owner_id": lead.owner_id,
    }


@router.post("/leads/assign/bulk", summary="Bulk assign leads to one CRM employee")
def bulk_assign_to_employee(
    data: BulkAssignToEmployeeRequest,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk assign leads")

    emp = (
        db.query(Employee)
        .filter(
            Employee.id == data.employee_id,
            Employee.status == "active",
        )
        .first()
    )
    if not emp:
        raise HTTPException(status_code=404, detail="Active employee not found")

    if not data.lead_ids:
        raise HTTPException(status_code=400, detail="No lead_ids provided")

    leads = db.query(Lead).filter(Lead.id.in_(data.lead_ids)).all()
    label = f"{emp.name} ({emp.employee_id})"
    for lead in leads:
        lead.assigned_employee_id = emp.id
        if emp.user_id is not None:
            lead.owner_id = emp.user_id
        _log_activity(db, lead.id, "ASSIGNED", f"Bulk assigned to employee {label}", user.id)

    db.commit()

    # Trigger Zoho CRM sync for each lead to update Owner
    try:
        from app.tasks.lead_tasks import sync_lead_to_zoho_task
        for lead in leads:
            sync_lead_to_zoho_task.delay(lead.id)
    except Exception as e:
        logger.error(f"Failed to trigger bulk Zoho sync: {e}")

    return {
        "message": f"Assigned {len(leads)} lead(s) to {label}",
        "assigned_count": len(leads),
        "assigned_employee_id": emp.id,
        "assigned_employee": {"id": emp.id, "employee_id": emp.employee_id, "name": emp.name},
        "owner_id": emp.user_id,
    }


@router.get("/leads", summary="Get role-based leads with filters")
def get_leads(
    status: Optional[str] = Query(None),
    lead_stage: Optional[str] = Query(
        None,
        description="CRM pipeline stage: new, contacted, interested, visit_scheduled, closed, lost",
    ),
    owner_id: Optional[int] = Query(None),
    source: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date, e.g. 2026-01-01"),
    date_to: Optional[str] = Query(None, description="ISO date, e.g. 2026-12-31"),
    limit: int = Query(
        10_000,
        ge=1,
        le=50_000,
        description="Max rows (default 10k so admin totals match /admin/analytics; was capped at 500)",
    ),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    """Get leads with optional filters. Admins see all. Others see leads they own (``owner_id``)
    or leads assigned to their CRM ``employees`` row (``employees.user_id`` → ``assigned_employee_id``).
    CSV imports often have no owner; assignment makes them visible to the right RM.
    """
    query = db.query(Lead).options(joinedload(Lead.assigned_employee))

    if user.role != "admin":
        emp_ids = [e.id for e in db.query(Employee).filter(Employee.user_id == user.id).all()]
        if emp_ids:
            query = query.filter(
                or_(Lead.owner_id == user.id, Lead.assigned_employee_id.in_(emp_ids))
            )
        else:
            query = query.filter(Lead.owner_id == user.id)

    if status:
        query = query.filter(Lead.status == status.lower())
    if lead_stage:
        query = query.filter(Lead.lead_stage == lead_stage.lower())
    if owner_id is not None:
        query = query.filter(Lead.owner_id == owner_id)
    if source:
        query = query.filter(Lead.source == source)
    if date_from:
        query = query.filter(Lead.created_at >= date_from)
    if date_to:
        query = query.filter(Lead.created_at <= date_to + " 23:59:59")

    # 🔥 Always sort UI by STAGE_PRIORITY
    stage_priority = case(
        {
            "New Lead / Prospect": 1,
            "Engaged": 2,
            "Follow Up": 3,
            "Visit Scheduled": 4,
            "Reserved": 5,
            "Dead": 6,
        },
        value=Lead.lead_stage,
        else_=99,
    )

    rows = (
        query.order_by(stage_priority.asc(), Lead.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Cache column names so we don't inspect per row (fixes timeout for limit=10000)
    columns = [col.key for col in sa_inspect(Lead).mapper.column_attrs]
    return [_lead_to_api_dict(lead, columns) for lead in rows]


def _crm_leads_visible_query(db: Session, user: User):
    """Same visibility rules as GET /leads (admin CRM list)."""
    q = db.query(Lead).options(joinedload(Lead.assigned_employee))
    if user.role != "admin":
        emp_ids = [e.id for e in db.query(Employee).filter(Employee.user_id == user.id).all()]
        if emp_ids:
            q = q.filter(or_(Lead.owner_id == user.id, Lead.assigned_employee_id.in_(emp_ids)))
        else:
            q = q.filter(Lead.owner_id == user.id)
    return q


@router.get("/leads/{lead_id}", summary="Get single lead (full CRM payload)")
def get_lead_full(lead_id: int, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    """Full lead row for admin detail (includes pipeline, Zoho, assigned employee). Prefer over GET /leads/{id}."""
    lead = _crm_leads_visible_query(db, user).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    columns = [col.key for col in sa_inspect(Lead).mapper.column_attrs]
    return _lead_to_api_dict(lead, columns)


@router.put("/leads/{lead_id}", summary="Unified atomic update for a lead")
def update_lead_unified(
    lead_id: int,
    req: LeadUpdateRequest,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    """
    Atomic update for lead fields (status, stage, priority, follow-up, assignment).
    Reduces frontend network overhead and prevents partial-save inconsistency.
    """
    lead = _crm_leads_visible_query(db, user).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    if req.status is not None:
        lead.status = req.status
    if req.lead_stage is not None:
        st = req.lead_stage.lower()
        if st not in VALID_LEAD_STAGES:
            raise HTTPException(status_code=400, detail=f"Invalid lead_stage: {st}")
        lead.lead_stage = st
    if req.priority is not None:
        lead.priority = req.priority
    if req.follow_up_at is not None:
        try:
            lead.follow_up_at = datetime.fromisoformat(req.follow_up_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ISO 8601 date format for follow_up_at")
    if req.assigned_employee_id is not None:
        emp = db.query(Employee).filter(Employee.id == req.assigned_employee_id).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")
        lead.assigned_employee_id = emp.id
        # Also sync owner_id to the user linked to this employee if exists
        if emp.user_id:
            lead.owner_id = emp.user_id
    if req.message is not None:
        lead.message = req.message
    if req.notes is not None:
        lead.notes = req.notes

    db.commit()
    db.refresh(lead)

    columns = [col.key for col in sa_inspect(Lead).mapper.column_attrs]
    return _lead_to_api_dict(lead, columns)


@router.get("/leads/export", summary="Export leads as CSV (filters)")
def export_leads_csv(
    source: Optional[str] = Query(None),
    lead_stage: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50_000, ge=1, le=100_000),
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    """Download UTF-8 CSV of leads with optional filters (same visibility rules as GET /leads)."""
    query = db.query(Lead).options(joinedload(Lead.assigned_employee))

    if user.role != "admin":
        emp_ids = [e.id for e in db.query(Employee).filter(Employee.user_id == user.id).all()]
        if emp_ids:
            query = query.filter(
                or_(Lead.owner_id == user.id, Lead.assigned_employee_id.in_(emp_ids))
            )
        else:
            query = query.filter(Lead.owner_id == user.id)

    if source:
        query = query.filter(Lead.source == source)
    if lead_stage:
        query = query.filter(Lead.lead_stage == lead_stage.lower())
    if status:
        query = query.filter(Lead.status == status.lower())
    if date_from:
        query = query.filter(Lead.created_at >= date_from)
    if date_to:
        query = query.filter(Lead.created_at <= date_to + " 23:59:59")

    rows = query.order_by(Lead.created_at.desc()).limit(limit).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "name",
            "phone",
            "email",
            "source",
            "city",
            "location",
            "project_name",
            "budget",
            "message",
            "status",
            "lead_stage",
            "crm_status",
            "reentry_count",
            "assigned_employee_id",
            "created_at",
        ]
    )
    for lead in rows:
        w.writerow(
            [
                lead.id,
                lead.name,
                lead.phone,
                lead.email,
                lead.source,
                lead.city,
                lead.location,
                lead.project_name,
                lead.budget,
                (lead.message or "")[:2000],
                getattr(lead.status, "value", lead.status),
                getattr(lead, "lead_stage", None),
                lead.crm_status,
                getattr(lead, "reentry_count", 0),
                lead.assigned_employee_id,
                lead.created_at.isoformat() if lead.created_at else "",
            ]
        )

    data = buf.getvalue()
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="leads_export.csv"'},
    )


def _log_activity(db: Session, lead_id: int, activity_type: str, message: str, user_id: Optional[int] = None):
    db.add(LeadActivity(lead_id=lead_id, type=activity_type, message=message, created_by=user_id))
    db.flush()


@router.put("/leads/{lead_id}/assign", summary="Assign single lead")
def assign_lead(lead_id: int, req: AssignLeadToRmRequest, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can assign leads")

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    rm = db.query(User).filter(User.id == req.rm_id).first()
    rm_name = (rm.full_name or rm.email) if rm else f"RM #{req.rm_id}"

    lead.owner_id = req.rm_id
    db.add(LeadAssignment(lead_id=lead.id, assigned_by=user.id, assigned_to=req.rm_id))
    _log_activity(db, lead.id, "ASSIGNED", f"Assigned to {rm_name}", user.id)

    db.commit()
    return {"message": "Assigned + logged"}


@router.put("/leads/bulk-assign", summary="Bulk assign leads")
def bulk_assign(data: BulkAssign, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can bulk assign leads")

    rm = db.query(User).filter(User.id == data.rm_id).first()
    rm_name = (rm.full_name or rm.email) if rm else f"RM #{data.rm_id}"

    leads = db.query(Lead).filter(Lead.id.in_(data.lead_ids)).all()
    for lead in leads:
        lead.owner_id = data.rm_id
        db.add(LeadAssignment(lead_id=lead.id, assigned_by=user.id, assigned_to=data.rm_id))
        _log_activity(db, lead.id, "ASSIGNED", f"Assigned to {rm_name}", user.id)

    batch = AssignmentBatch(
        total_leads=len(leads),
        rm_count=1,
        strategy="manual_bulk",
        distribution={rm_name: len(leads)},
        created_by=user.id,
    )
    db.add(batch)
    db.commit()
    return {"message": f"Bulk assigned {len(leads)} leads", "batch_id": batch.id}


@router.post("/leads/auto-assign", summary="Auto-assign leads with load balancing across RMs")
def auto_assign_leads(
    req: AutoAssignRequest,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can auto-assign leads")

    if req.rm_ids:
        rm_list = db.query(User).filter(User.id.in_(req.rm_ids), User.is_active == True).all()
    else:
        rm_list = db.query(User).filter(User.role.in_(["RM", "employee"]), User.is_active == True).all()

    if not rm_list:
        raise HTTPException(status_code=400, detail="No active RMs available for assignment")

    lead_query = (
        db.query(Lead)
        .filter(Lead.owner_id.is_(None), Lead.assigned_employee_id.is_(None))
        .with_for_update()
    )
    if req.lead_ids:
        lead_query = lead_query.filter(Lead.id.in_(req.lead_ids))

    leads = lead_query.order_by(Lead.priority.desc(), Lead.created_at.asc()).all()

    if not leads:
        return {"message": "No unassigned leads to distribute", "total_assigned": 0, "distribution": {}}

    active_statuses = {"new", "contacted", "interested", "qualified", "followup"}
    load_rows = (
        db.query(User.id, func.count(Lead.id).label("cnt"))
        .outerjoin(Lead, (Lead.owner_id == User.id) & Lead.status.in_(active_statuses))
        .filter(User.id.in_([rm.id for rm in rm_list]))
        .group_by(User.id)
        .all()
    )
    rm_load = {r.id: int(r.cnt or 0) for r in load_rows}
    rm_map = {rm.id: rm for rm in rm_list}

    use_load_balance = req.strategy == "load_balanced"
    strategy_label = "load-balanced" if use_load_balance else "round-robin"

    summary = []
    for idx, lead in enumerate(leads):
        if use_load_balance:
            target_id = min(rm_load, key=lambda rid: rm_load.get(rid, 0))
            rm_load[target_id] = rm_load.get(target_id, 0) + 1
        else:
            target_id = rm_list[idx % len(rm_list)].id

        rm = rm_map[target_id]
        rm_name = rm.full_name or rm.email
        lead.owner_id = rm.id
        db.add(LeadAssignment(lead_id=lead.id, assigned_by=user.id, assigned_to=rm.id))
        _log_activity(db, lead.id, "ASSIGNED", f"Auto-assigned to {rm_name} ({strategy_label})", user.id)
        summary.append({"lead_id": lead.id, "rm_id": rm.id, "rm_name": rm_name})

    per_rm = {}
    for s in summary:
        name = s["rm_name"]
        per_rm[name] = per_rm.get(name, 0) + 1

    batch = AssignmentBatch(
        total_leads=len(leads),
        rm_count=len(rm_list),
        strategy="load_balanced" if use_load_balance else "round_robin",
        distribution=per_rm,
        created_by=user.id,
    )
    db.add(batch)

    db.commit()

    return {
        "message": f"Auto-assigned {len(leads)} leads across {len(rm_list)} RMs ({strategy_label})",
        "total_assigned": len(leads),
        "distribution": per_rm,
        "batch_id": batch.id,
        "strategy": strategy_label,
    }


@router.get("/leads/{lead_id}/assignments", summary="Get assignment history for a lead")
def get_assignment_history(lead_id: int, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    assignments = (
        db.query(LeadAssignment)
        .options(
            joinedload(LeadAssignment.assigner),
            joinedload(LeadAssignment.assignee),
        )
        .filter(LeadAssignment.lead_id == lead_id)
        .order_by(LeadAssignment.assigned_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "lead_id": a.lead_id,
            "assigned_by": a.assigned_by,
            "assigned_by_name": a.assigner.full_name or a.assigner.email if a.assigner else None,
            "assigned_to": a.assigned_to,
            "assigned_to_name": a.assignee.full_name or a.assignee.email if a.assignee else None,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
        }
        for a in assignments
    ]


@router.put("/leads/{lead_id}/status", summary="Update lead status")
def update_lead_status(lead_id: int, req: UpdateLeadStatusRequest, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    status = req.status.lower()
    if status not in VALID_LEAD_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(VALID_LEAD_STATUSES))}")

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old_status = lead.status
    lead.status = status
    _log_activity(db, lead.id, "STATUS_CHANGED", f"Status changed from {old_status} to {status}", user.id)

    db.commit()
    return {"message": "Status updated", "status": status}


@router.put("/leads/{lead_id}/stage", summary="Update CRM pipeline stage")
def update_lead_stage(
    lead_id: int,
    req: UpdateLeadStageRequest,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    stage = req.lead_stage.strip().lower()
    if stage not in VALID_LEAD_STAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid lead_stage. Allowed: {', '.join(sorted(VALID_LEAD_STAGES))}",
        )

    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    old = getattr(lead, "lead_stage", None) or "new"
    lead.lead_stage = stage
    _log_activity(
        db,
        lead.id,
        "STAGE_CHANGED",
        f"Pipeline stage changed from {old} to {stage}",
        user.id,
    )
    db.commit()
    return {"message": "Stage updated", "lead_stage": stage}


@router.get("/leads/{lead_id}/timeline", summary="Full activity timeline for a lead")
def get_lead_timeline(lead_id: int, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    activities = (
        db.query(LeadActivity)
        .options(joinedload(LeadActivity.user))
        .filter(LeadActivity.lead_id == lead_id)
        .order_by(LeadActivity.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "id": a.id,
            "lead_id": a.lead_id,
            "type": a.type,
            "message": a.message,
            "created_by": a.created_by,
            "created_by_name": (a.user.full_name or a.user.email) if a.user else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in activities
    ]


@router.put("/leads/{lead_id}/followup", summary="Set follow-up reminder")
def set_followup(lead_id: int, req: SetFollowUpRequest, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        dt = datetime.fromisoformat(req.follow_up_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format. Use ISO 8601.")

    lead.follow_up_at = dt
    _log_activity(db, lead.id, "FOLLOWUP_SET", f"Follow-up set for {dt.strftime('%d %b %Y %I:%M %p')}", user.id)
    db.commit()
    return {"message": "Follow-up set", "follow_up_at": dt.isoformat()}


@router.post("/leads/{lead_id}/notes", summary="Add a note to a lead")
def add_note(lead_id: int, req: AddNoteRequest, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    _log_activity(db, lead.id, "NOTE", req.note, user.id)
    db.commit()
    return {"message": "Note added"}


@router.put("/leads/{lead_id}/priority", summary="Set lead priority")
def update_priority(lead_id: int, req: UpdatePriorityRequest, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    lead = db.query(Lead).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    label_map = {p["value"]: p["label"] for p in PRIORITY_LEVELS}
    old_label = label_map.get(lead.priority or 1, "Low")
    new_label = label_map.get(req.priority, "Low")

    lead.priority = req.priority
    _log_activity(db, lead.id, "STATUS_CHANGED", f"Priority changed from {old_label} to {new_label}", user.id)
    db.commit()
    return {"message": "Priority updated", "priority": req.priority}


@router.put("/leads/{lead_id}/message", summary="Update lead enquiry message")
def update_lead_message(
    lead_id: int,
    req: UpdateLeadMessageRequest,
    db: Session = Depends(get_mysql_db),
    user=Depends(security.get_current_user),
):
    lead = _crm_leads_visible_query(db, user).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if req.message is None:
        lead.message = None
    else:
        m = req.message.strip()
        lead.message = m[:2000] if m else None
    _log_activity(db, lead.id, "NOTE", "Enquiry message updated", user.id)
    db.commit()
    lead = _crm_leads_visible_query(db, user).filter(Lead.id == lead_id).first()
    columns = [col.key for col in sa_inspect(Lead).mapper.column_attrs]
    return _lead_to_api_dict(lead, columns)


@router.delete("/leads/{lead_id}", summary="Delete a lead")
def delete_lead(lead_id: int, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    lead = _crm_leads_visible_query(db, user).filter(Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    db.query(LeadEvent).filter(LeadEvent.lead_id == lead_id).delete(synchronize_session=False)
    db.query(LeadActivity).filter(LeadActivity.lead_id == lead_id).delete(synchronize_session=False)
    db.query(LeadAssignment).filter(LeadAssignment.lead_id == lead_id).delete(synchronize_session=False)
    db.query(RetellCall).filter(RetellCall.lead_id == lead_id).update({RetellCall.lead_id: None}, synchronize_session=False)
    db.delete(lead)
    db.commit()
    return {"message": "Lead deleted"}


@router.get("/assignment-batches", summary="Assignment batch history")
def get_assignment_batches(db: Session = Depends(get_mysql_db), _admin=Depends(security.admin_required)):
    batches = (
        db.query(AssignmentBatch)
        .options(joinedload(AssignmentBatch.creator))
        .order_by(AssignmentBatch.created_at.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": b.id,
            "total_leads": b.total_leads,
            "rm_count": b.rm_count,
            "strategy": b.strategy,
            "distribution": b.distribution,
            "created_by_name": (b.creator.full_name or b.creator.email) if b.creator else None,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in batches
    ]


@router.get("/funnel", summary="Conversion funnel counts")
def conversion_funnel(db: Session = Depends(get_mysql_db), _admin=Depends(security.admin_required)):
    """Count of leads at each pipeline stage — labels/tones from lead_schema (aligned with DB)."""
    rows = db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all()
    counts = {str(s): c for s, c in rows}
    return [
        {
            "stage": s,
            "count": counts.get(s, 0),
            "label": LEAD_STATUS_LABELS.get(s, s.replace("_", " ").title()),
            "tone": LEAD_STATUS_TONES.get(s, "muted"),
        }
        for s in LEAD_STATUS_ORDER
    ]


@router.get("/workload", summary="RM workload overview")
def rm_workload(db: Session = Depends(get_mysql_db), _admin=Depends(security.admin_required)):
    """Active leads and overdue follow-ups per RM."""
    now = datetime.now(timezone.utc)
    active_statuses = {"new", "contacted", "interested", "qualified", "followup"}

    rows = (
        db.query(
            User.id,
            User.full_name,
            User.email,
            func.count(Lead.id).label("active_leads"),
            func.sum(
                case(
                    (Lead.follow_up_at <= now, 1),
                    else_=0,
                )
            ).label("overdue_followups"),
            func.sum(
                case(
                    (Lead.follow_up_at > now, 1),
                    else_=0,
                )
            ).label("upcoming_followups"),
        )
        .outerjoin(Lead, (Lead.owner_id == User.id) & Lead.status.in_(active_statuses))
        .filter(User.role.in_(["RM", "employee"]))
        .group_by(User.id)
        .all()
    )
    return [
        {
            "rm_id": r.id,
            "name": r.full_name or r.email,
            "active_leads": r.active_leads,
            "overdue_followups": int(r.overdue_followups or 0),
            "upcoming_followups": int(r.upcoming_followups or 0),
        }
        for r in rows
    ]


@router.get("/performance", summary="RM performance dashboard")
def rm_performance(db: Session = Depends(get_mysql_db), _admin=Depends(security.admin_required)):
    """Per-RM lead totals, conversions, and conversion rate."""
    rows = (
        db.query(
            User.id,
            User.full_name,
            User.email,
            func.count(Lead.id).label("total"),
            func.sum(case((Lead.status == "converted", 1), else_=0)).label("converted"),
        )
        .outerjoin(Lead, Lead.owner_id == User.id)
        .filter(User.role.in_(["RM", "employee"]))
        .group_by(User.id)
        .all()
    )
    return [
        {
            "rm_id": r.id,
            "name": r.full_name or r.email,
            "total_leads": r.total,
            "converted": int(r.converted or 0),
            "conversion_rate": round((int(r.converted or 0) / r.total) * 100, 1) if r.total else 0,
        }
        for r in rows
    ]
