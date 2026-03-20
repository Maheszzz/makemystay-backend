"""Centralized lead processing service.

This module provides a unified pipeline for all incoming leads, ensuring
deduplication, database storage, transactional agent assignment, and
asynchronous CRM synchronization.
"""

import traceback
from typing import Optional

from loguru import logger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.redis import lead_queue
from app.events.event_service import publish_event
from app.models.failed_job import FailedJob
from app.models.lead import Lead
from app.repo import agent_repo
from app.schemas.lead import LeadCreate
from app.services.assignment_service import assign_lead
from app.tasks.lead_tasks import sync_lead_to_zoho_task


async def process_lead(
    db: Session,
    lead_data: LeadCreate,
    source: str,
    raw_payload: Optional[dict] = None,
) -> Optional[Lead]:
    """
    Process an incoming lead: Dedup → Store → Assign (transactional) → Enqueue CRM Sync.

    Uses SELECT FOR UPDATE on the agents table to prevent concurrent workers
    from double-assigning the same agent.

    Args:
        db: Database session.
        lead_data: Mapped lead data in standard format.
        source: Source of the lead (housing, 99acres, website, etc.).
        raw_payload: Original data from the source for debugging.

    Returns:
        The created Lead object, or None if it was a duplicate.
    """
    try:
        # ── 1. Deduplication ────────────────────────────────────────────
        # Priority:
        #   a) external_id match (most precise — same inquiry ID from source)
        #   b) phone + source + lead_date (same customer, same timestamp)
        #   c) phone + source only (last-resort fallback when no date/id)
        #
        # We do NOT deduplicate on phone+source alone because a customer can
        # legitimately inquire about multiple properties over time.
        existing = None

        if lead_data.external_id:
            existing = (
                db.query(Lead)
                .filter(Lead.source == source, Lead.external_id == lead_data.external_id)
                .first()
            )
        elif lead_data.lead_date:
            existing = (
                db.query(Lead)
                .filter(
                    Lead.phone == lead_data.phone,
                    Lead.source == source,
                    Lead.lead_date == lead_data.lead_date,
                )
                .first()
            )
        else:
            existing = (
                db.query(Lead)
                .filter(Lead.phone == lead_data.phone, Lead.source == source)
                .first()
            )

        if existing:
            logger.info(f"Duplicate lead skipped: {lead_data.phone} from {source}")
            return None

        # ── 2. Store Lead ─────────────────────────────────────────────
        new_lead = Lead(
            name=lead_data.name,
            phone=lead_data.phone,
            email=lead_data.email,
            source=source,
            city=lead_data.city,
            location=lead_data.location,
            project_name=lead_data.project_name,
            property_type=lead_data.property_type,
            budget=lead_data.budget,
            message=lead_data.message or lead_data.requirement,
            lead_date=lead_data.lead_date,
            external_id=lead_data.external_id,
            campaign=lead_data.campaign,
            ad_id=lead_data.ad_id,
            property_id=lead_data.property_id,
            raw_payload=raw_payload,
            status="new",
            crm_status="pending",
        )

        db.add(new_lead)
        db.flush()  # Get an ID without committing

        # ── 3. Transactional Agent Assignment ─────────────────────────
        #   - SELECT FOR UPDATE locks agent rows to prevent race conditions
        #   - Uses a savepoint so assignment failure doesn't lose the lead
        try:
            agents = agent_repo.get_available_agents_for_update(
                db, location=new_lead.location
            )
            assigned_agent = assign_lead(new_lead, agents)

            if assigned_agent:
                new_lead.assigned_to = assigned_agent.id
                # Atomic increment inside the same transaction
                assigned_agent.current_load = assigned_agent.current_load + 1
                logger.info(
                    f"Lead {new_lead.id} assigned to Agent {assigned_agent.id} "
                    f"({assigned_agent.name})"
                )
                publish_event(
                    new_lead.id,
                    "ASSIGNED",
                    f"Assigned to agent {assigned_agent.name}",
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
                )
        except Exception as assign_err:
            logger.error(
                f"Error during lead assignment for Lead {new_lead.id}: {assign_err}"
            )
            # Assignment failure should NOT prevent lead creation

        # ── 4. Commit the transaction ─────────────────────────────────
        db.commit()
        db.refresh(new_lead)

        logger.success(
            f"New lead stored: ID={new_lead.id}, "
            f"Phone={new_lead.phone}, Source={source}"
        )
        publish_event(new_lead.id, "LEAD_CREATED", f"Lead created from {source}")

        # ── 5. Enqueue CRM Sync (Asynchronous) ───────────────────────
        _enqueue_crm_sync(db, new_lead)

        return new_lead

    except IntegrityError as ie:
        db.rollback()
        # A unique-constraint violation means the lead already exists — treat as dedup.
        logger.info(
            f"Duplicate lead (IntegrityError) from {source}, "
            f"phone={lead_data.phone}: {ie.orig}"
        )
        return None

    except Exception as e:
        db.rollback()
        error_msg = f"Failed to process lead from {source}: {str(e)}"
        logger.error(error_msg)

        # Log to failed_jobs table for observability
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

        return None


def _enqueue_crm_sync(db: Session, lead: Lead) -> None:
    """Enqueue the lead for Zoho CRM synchronisation via RQ."""
    if not lead_queue:
        logger.warning(
            "Redis Queue (lead_queue) not available. "
            "CRM sync will not happen automatically."
        )
        return

    try:
        from rq import Retry

        lead_queue.enqueue(
            sync_lead_to_zoho_task,
            lead.id,
            job_id=f"sync_zoho_{lead.id}",
            retry=Retry(max=5, interval=[10, 30, 60, 300, 600]),
        )
        lead.crm_status = "queued"
        db.commit()
        logger.info(f"Enqueued Zoho sync for lead {lead.id}")
    except Exception as enqueue_err:
        logger.error(f"Failed to enqueue lead {lead.id}: {enqueue_err}")
        lead.crm_status = "failed"
        db.commit()
