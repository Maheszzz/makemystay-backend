"""Centralized lead processing service.

Dedup (global phone) → merge re-entry or create → RM rules → agent assign → Zoho queue.
"""

import traceback
from datetime import datetime, timezone
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.events.event_service import publish_event
from app.models.failed_job import FailedJob
from app.models.lead import Lead
from app.models.lead_activity import LeadActivity
from app.models.lead_event import LeadEvent
from app.repo import agent_repo
from app.schemas.lead import LeadCreate
import json
from app.services.assignment_service import assign_lead
from app.services.crm_employee_assignment import try_assign_employee_by_city_rules
from datetime import timedelta


def normalize_phone(phone: str) -> str:
    """Normalize phone number to purely digits without country prefix zeros or +91."""
    if not phone:
        return ""
    phone = str(phone).replace(" ", "").replace("-", "")
    if phone.startswith("+91"):
        phone = phone[3:]
    if phone.startswith("0"):
        phone = phone[1:]
    return phone


def _merge_reentry_lead(
    existing: Lead,
    lead_data: LeadCreate,
    source: str,
    raw_payload: Optional[dict],
) -> None:
    """Update an existing lead when the same phone enquires again."""
    now = datetime.now(timezone.utc)
    
    # 🔴 Elite Improvement: 5-minute Cooldown Logic
    # If the lead re-enters within 5 mins, we don't increment inquiry_count (prevents bot spam)
    should_increment = True
    if existing.last_reentry_at:
        diff = (now - existing.last_reentry_at.replace(tzinfo=timezone.utc)).total_seconds()
        if diff < 300: # 5 minutes
            should_increment = False
            logger.info(f"Re-entry cooldown active for lead {existing.id} (diff: {diff:.1f}s). Skipping inquiry_count increment.")

    if should_increment:
        existing.inquiry_count = (existing.inquiry_count or 0) + 1
        existing.reentry_count = (existing.reentry_count or 0) + 1
        existing.last_reentry_at = now

    existing.last_contacted_at = now
    existing.last_activity_at = now
    existing.source = source
    
    # 🔥 RESET STATUS (Guard: Don't downgrade high-quality leads)
    high_quality_statuses = {"contacted", "interested", "hot", "site_visit", "converted"}
    current_status = (existing.status or "").lower()
    
    # Only reset to 'new' if they aren't already progressed
    if not any(hq in current_status for hq in high_quality_statuses):
        existing.status = "new"
        existing.lead_stage = "New Lead / Prospect"
        existing.sub_status = None
        existing.follow_up_at = None
    else:
        logger.info(f"Consistency Guard: Skipping status reset for progressed lead {existing.id} (Status: {existing.status})")
    
    if lead_data.name:
        existing.name = lead_data.name
    if lead_data.email:
        existing.email = lead_data.email
    if lead_data.city:
        existing.city = lead_data.city
    if lead_data.location:
        existing.location = lead_data.location
    if lead_data.project_name:
        existing.project_name = lead_data.project_name
    if lead_data.property_type:
        existing.property_type = lead_data.property_type
    if lead_data.budget:
        existing.budget = lead_data.budget
    if lead_data.external_id:
        existing.external_id = lead_data.external_id
    msg = lead_data.message or lead_data.requirement
    if msg:
        prev = (existing.message or "").strip()
        block = f"{source}: {msg}"
        if prev:
            existing.message = f"{prev}\n--- Re-entry ---\n{block}"[:12000]
        else:
            existing.message = block[:8000]
    if raw_payload is not None:
        existing.raw_payload = raw_payload
    existing.crm_status = "pending"


async def process_lead(
    db: Session,
    lead_data: LeadCreate,
    source: str,
    raw_payload: Optional[dict] = None,
    *,
    raise_on_failure: bool = False,
    csv_import_stagger_index: Optional[int] = None,
    sync_to_zoho: bool = True,
    send_whatsapp: bool = True,
    trigger_ai: bool = True,
) -> Optional[Lead]:
    """
    Process an incoming lead.

    If the phone already exists, the existing row is **updated** (re-entry), an activity is
    logged, CRM sync is re-queued when ``sync_to_zoho`` is True, and that lead is returned
    (``reentry_count`` > 0). ``None`` is returned only on integrity races or hard failures.
    """
    # Normalize phone for identity lock
    norm_phone = normalize_phone(lead_data.phone)
    
    try:
        # Identity-level lookup (unbreakable)
        lead = db.query(Lead).filter(
            Lead.normalized_phone == norm_phone,
            Lead.is_deleted == False
        ).with_for_update().first()

        if lead:
            # 🔥 EXISTING USER → UPDATE (UPSERT)
            logger.info(f"Re-entry detected for phone {norm_phone} (Lead ID: {lead.id})")
            _merge_reentry_lead(lead, lead_data, source, raw_payload)
            
            # ELITE: Log Re-entry Event
            event = LeadEvent(
                lead_id=lead.id,
                event_type="LEAD_REENTERED",
                message=f"Lead re-entered via {source}",
                payload=json.dumps(raw_payload) if raw_payload else None
            )
            db.add(event)
            db.add(
                LeadActivity(
                    lead_id=lead.id,
                    type="DUPLICATE_REENTRY",
                    message=f"Re-enquired from {source}",
                )
            )
            try_assign_employee_by_city_rules(db, lead)
            db.commit()
            db.refresh(lead)

            publish_event(
                lead.id,
                "LEAD_REENTRY",
                f"Duplicate inbound merged from {source}",
                payload={"source": source, "reentry_count": lead.reentry_count},
                session=db,
            )

            if sync_to_zoho:
                _enqueue_crm_sync(db, lead, csv_stagger_index=csv_import_stagger_index)
            return lead

        # ✨ NEW USER → CREATE
        logger.info(f"New lead detected for phone {norm_phone}")
        
        if lead_data.lead_date:
            lead_ts = int(lead_data.lead_date)
        else:
            lead_ts = int(datetime.now(timezone.utc).timestamp())

        new_lead = Lead(
            name=lead_data.name,
            phone=lead_data.phone, # Store raw
            normalized_phone=norm_phone, # Store normalized for UNIQUE constraint
            email=lead_data.email,
            source=source,
            city=lead_data.city,
            location=lead_data.location,
            project_name=lead_data.project_name,
            property_type=lead_data.property_type,
            budget=lead_data.budget,
            message=lead_data.message or lead_data.requirement,
            lead_date=lead_ts,
            external_id=lead_data.external_id,
            campaign=lead_data.campaign,
            ad_id=lead_data.ad_id,
            property_id=lead_data.property_id,
            raw_payload=raw_payload,
            status="new",
            lead_stage="New Lead / Prospect",
            inquiry_count=1,
            reentry_count=0,
            last_activity_at=datetime.now(timezone.utc),
            last_reentry_at=datetime.now(timezone.utc),
            crm_status="pending"
        )
        db.add(new_lead)
        db.flush() # Get ID
        
        # ELITE: Log Creation Event
        event = LeadEvent(
            lead_id=new_lead.id,
            event_type="LEAD_CREATED",
            message=f"Lead created via {source}",
            payload=json.dumps(raw_payload) if raw_payload else None
        )
        db.add(event)
        db.add(
            LeadActivity(
                lead_id=new_lead.id,
                type="CREATED",
                message=f"Lead ingested from {source}",
            )
        )

        try_assign_employee_by_city_rules(db, new_lead)

        try:
            agents = agent_repo.get_available_agents_for_update(
                db, location=new_lead.location
            )
            assigned_agent = assign_lead(new_lead, agents)

            if assigned_agent:
                new_lead.assigned_to = assigned_agent.id
                assigned_agent.current_load = assigned_agent.current_load + 1
                logger.info(
                    f"Lead {new_lead.id} assigned to Agent {assigned_agent.id} "
                    f"({assigned_agent.name})"
                )
                publish_event(
                    new_lead.id,
                    "ASSIGNED",
                    f"Assigned to agent {assigned_agent.name}",
                    session=db,
                )
            else:
                logger.warning(
                    f"No available agents for Lead {new_lead.id}. "
                    "Remaining unassigned."
                )
                publish_event(
                    new_lead.id,
                    "UNASSIGNED",
                    "No available agents for assignment",
                    session=db,
                )
        except Exception as assign_err:
            logger.error(
                f"Error during lead assignment for Lead {new_lead.id}: {assign_err}"
            )

        db.commit()
        db.refresh(new_lead)

        logger.success(
            f"New lead stored: ID={new_lead.id}, "
            f"Phone={new_lead.phone}, Source={source}"
        )
        publish_event(
            new_lead.id,
            "LEAD_CREATED",
            f"Lead created from {source}",
            payload={
                "id": new_lead.id,
                "name": new_lead.name,
                "phone": new_lead.phone,
                "email": new_lead.email,
                "source": new_lead.source,
                "project_name": new_lead.project_name,
                "property_id": new_lead.property_id,
                "status": new_lead.status,
                "created_at": (
                    new_lead.created_at.isoformat() if new_lead.created_at else None
                ),
            },
            session=db,
        )

        if sync_to_zoho:
            _enqueue_crm_sync(db, new_lead, csv_stagger_index=csv_import_stagger_index)

        if send_whatsapp:
            _enqueue_whatsapp(db, new_lead, csv_stagger_index=csv_import_stagger_index)

        return new_lead

    except IntegrityError as ie:
        db.rollback()
        logger.warning(
            f"Duplicate lead (IntegrityError) from {source}, "
            f"phone={lead_data.phone}. Potential race condition. Engaging merge logic: {ie.orig}"
        )
        # Use normalized phone for recovery lookup
        norm_phone = normalize_phone(lead_data.phone)
        existing = db.query(Lead).filter(
            Lead.normalized_phone == norm_phone,
            Lead.is_deleted == False
        ).first()
        
        if existing:
            logger.info("Recovered from race condition — merging re-entry.")
            _merge_reentry_lead(existing, lead_data, source, raw_payload)
            
            # ELITE: Log Re-entry Event
            event = LeadEvent(
                lead_id=existing.id,
                event_type="LEAD_REENTERED",
                message=f"Lead re-entered via {source} (Race Condition Recovered)",
                payload=json.dumps(raw_payload) if raw_payload else None
            )
            db.add(event)
            db.add(
                LeadActivity(
                    lead_id=existing.id,
                    type="DUPLICATE_REENTRY",
                    message=f"Re-enquired from {source} (Race Condition Recovered)",
                )
            )
            try_assign_employee_by_city_rules(db, existing)
            db.commit()
            db.refresh(existing)
            publish_event(
                existing.id,
                "LEAD_REENTRY",
                f"Duplicate inbound merged from {source}",
                payload={"source": source, "reentry_count": existing.reentry_count},
                session=db,
            )
            if sync_to_zoho:
                _enqueue_crm_sync(db, existing, csv_stagger_index=csv_import_stagger_index)
            return existing
        return None

    except Exception as e:
        db.rollback()
        error_msg = f"Failed to process lead from {source}: {str(e)}"
        logger.error(error_msg)

        try:
            failed = FailedJob(
                job_name=f"process_lead_{source}",
                payload={
                    "lead_data": lead_data.model_dump(),
                    "raw_payload": raw_payload,
                },
                error=str(e),
                stack_trace=traceback.format_exc(),
            )
            db.add(failed)
            db.commit()
        except Exception as log_err:
            logger.error(f"Failed to record failed job: {log_err}")

        if raise_on_failure:
            raise
        return None


def _should_sync_to_zoho(lead: Lead, force: bool = False) -> bool:
    """Determine if a lead should be synced to Zoho CRM based on cooldown rules."""
    if force:
        return True
    
    # New leads always sync
    if not lead.zoho_synced or not lead.zoho_lead_id:
        return True
        
    # Re-entries: 1 hour cooldown if no major changes
    if lead.last_zoho_sync_at:
        now = datetime.now(timezone.utc)
        # Ensure last_zoho_sync_at is timezone-aware for comparison
        last_sync = lead.last_zoho_sync_at
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)
            
        diff = (now - last_sync).total_seconds()
        if diff < 3600: # 1 hour
            logger.info(
                f"Zoho Sync | lead_id={lead.id} | zoho_id={lead.zoho_lead_id or '-'} | skipped=cooldown | age_s={diff:.1f}"
            )
            return False
            
    return True


def _enqueue_crm_sync(db: Session, lead: Lead, *, csv_stagger_index: Optional[int] = None, force: bool = False) -> None:
    """Enqueue Zoho CRM sync. 
    
    High-volume sources (housing, 99acres, csv) are marked as 'pending' for batch processing.
    Direct sources (website) are still queued immediately for low latency.
    """
    if not _should_sync_to_zoho(lead, force=force):
        return

    # High-volume sources get batch-processed to save API credits
    batch_sources = {"housing", "99acres", "magicbricks", "csv", "lead_import"}
    
    if lead.source and lead.source.lower() in batch_sources:
        lead.crm_status = "pending"
        db.commit()
        logger.info(f"Lead {lead.id} marked as 'pending' for Zoho batch sync (source: {lead.source})")
        return

    try:
        from app.services.celery_queue_monitor import get_backpressure_delay_seconds
        from app.tasks.lead_tasks import sync_lead_to_zoho_task

        backpressure = get_backpressure_delay_seconds()
        if csv_stagger_index is not None:
            countdown = int(min(float(csv_stagger_index) * 0.2, 600.0) + backpressure)
        else:
            countdown = int(backpressure)

        sync_lead_to_zoho_task.apply_async(args=[lead.id], countdown=countdown)

        lead.crm_status = "queued"
        db.commit()
        logger.info(f"Enqueued Zoho sync for lead {lead.id}")
    except Exception as enqueue_err:
        logger.error(f"Failed to enqueue lead {lead.id}: {enqueue_err}")
        lead.crm_status = "failed"
        db.commit()


def _enqueue_whatsapp(db: Session, lead: Lead, *, csv_stagger_index: Optional[int] = None) -> None:
    """Enqueue WhatsApp notification (Celery)."""
    try:
        from app.tasks.lead_tasks import send_lead_whatsapp_task

        if csv_stagger_index is not None:
            # Staggered: 0.2s, 0.4s, ... max 10 mins. Stagger differently from Zoho to spread load.
            countdown = min(float(csv_stagger_index) * 0.3, 600.0)
            send_lead_whatsapp_task.apply_async(args=[lead.id], countdown=countdown)
        else:
            send_lead_whatsapp_task.delay(lead.id)

        logger.info(f"Enqueued WhatsApp for lead {lead.id}")
    except Exception as e:
        logger.error(f"Failed to enqueue WhatsApp for lead {lead.id}: {e}")


def _enqueue_ai_call(db: Session, lead: Lead, *, csv_stagger_index: Optional[int] = None) -> None:
    """Enqueue AI call (Celery)."""
    try:
        from app.tasks.lead_tasks import trigger_lead_ai_call_task

        if csv_stagger_index is not None:
            # Staggered: 0.5s, 1.0s, ... max 15 mins. AI calls are heavier, stagger more.
            countdown = min(float(csv_stagger_index) * 0.5, 900.0)
            trigger_lead_ai_call_task.apply_async(args=[lead.id], countdown=countdown)
        else:
            trigger_lead_ai_call_task.delay(lead.id)

        logger.info(f"Enqueued AI call for lead {lead.id}")
    except Exception as e:
        logger.error(f"Failed to enqueue AI call for lead {lead.id}: {e}")
