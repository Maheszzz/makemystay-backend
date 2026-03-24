"""
CRM / leads admin: metadata, RMs, lead CRUD, assignments, timeline, funnel, workload.
"""

import asyncio
from datetime import date, datetime, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import case, func
from sqlalchemy.orm import Session, joinedload

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.log_dedupe import should_log_once
from app.core.rate_limit import limiter
from app.core.redis import lead_queue
from app.core.lead_schema import (
    VALID_LEAD_STATUSES,
    build_lead_metadata_payload,
    LEAD_STATUS_LABELS,
    LEAD_STATUS_ORDER,
    LEAD_STATUS_TONES,
    PRIORITY_LEVELS,
)
from app.models.assignment_batch import AssignmentBatch
from app.models.lead import Lead
from app.models.realty import Property
from app.models.lead_activity import LeadActivity
from app.models.lead_assignment import LeadAssignment
from app.models.sync_metadata import SyncMetadata
from app.models.user import User

from app.api.admin.schemas import (
    AddNoteRequest,
    AssignLeadRequest,
    AutoAssignRequest,
    BulkAssign,
    SetFollowUpRequest,
    UpdateLeadStatusRequest,
    UpdatePriorityRequest,
)

router = APIRouter()


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


@router.get("/admin/lead-metadata", summary="Lead statuses, priorities (single source for admin UI)")
def get_lead_metadata(user=Depends(security.get_current_user)):
    """Returns labels and options derived from the Lead model / DB enum — no hardcoding in the frontend."""
    if user.role not in ["admin", "RM", "employee"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return build_lead_metadata_payload()


@router.get("/admin/stats", summary="Get lead ingestion statistics")
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


@router.get("/admin/analytics", summary="Get simple analytics metrics")
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

        return {
            "total_leads": total_leads,
            "today_leads": today_leads,
            "failed": failed,
            "failed_lead_ids": failed_lead_ids,
            "total_properties": total_properties,
            "active_properties": active_properties,
            "properties_added_this_month": properties_added_this_month,
            "properties_added_last_month": properties_added_last_month,
            "leads_this_month": leads_this_month,
            "leads_last_month": leads_last_month,
        }

    try:
        data = await asyncio.wait_for(asyncio.to_thread(_fetch_data), timeout=5.0)
        return data
    except asyncio.TimeoutError:
        return {"error": "timeout"}
    except Exception as e:
        if should_log_once("error:/admin/analytics", window_seconds=60):
            logger.error(f"Failed to fetch analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")


@router.get("/users/rms", summary="Get all active Relationship Managers")
def get_rms(db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
    """Fetch active users with the RM or employee role for the assignment dropdown."""
    if user.role not in ["admin", "employee"]:
        raise HTTPException(status_code=403, detail="Not allowed")
    return db.query(User).filter(User.role == "employee").all()


@router.get("/leads", summary="Get role-based leads with filters")
def get_leads(
    status: Optional[str] = Query(None),
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
    """Get leads with optional filters. Admins see all, RMs see only their assigned leads."""
    query = db.query(Lead)

    if user.role != "admin":
        query = query.filter(Lead.owner_id == user.id)

    if status:
        query = query.filter(Lead.status == status.lower())
    if owner_id is not None:
        query = query.filter(Lead.owner_id == owner_id)
    if source:
        query = query.filter(Lead.source == source)
    if date_from:
        query = query.filter(Lead.created_at >= date_from)
    if date_to:
        query = query.filter(Lead.created_at <= date_to + " 23:59:59")

    return query.order_by(Lead.created_at.desc()).offset(offset).limit(limit).all()


def _log_activity(db: Session, lead_id: int, activity_type: str, message: str, user_id: Optional[int] = None):
    db.add(LeadActivity(lead_id=lead_id, type=activity_type, message=message, created_by=user_id))
    db.flush()


@router.put("/leads/{lead_id}/assign", summary="Assign single lead")
def assign_lead(lead_id: int, req: AssignLeadRequest, db: Session = Depends(get_mysql_db), user=Depends(security.get_current_user)):
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

    lead_query = db.query(Lead).filter(Lead.owner_id == None).with_for_update()
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


@router.get("/admin/assignment-batches", summary="Assignment batch history")
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


@router.get("/admin/funnel", summary="Conversion funnel counts")
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


@router.get("/admin/workload", summary="RM workload overview")
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


@router.get("/admin/performance", summary="RM performance dashboard")
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
