"""Centralized lead processing service.

This module provides a unified pipeline for all incoming leads, ensuring
deduplication, database storage, and asynchronous CRM synchronization.
"""

import traceback
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.redis import lead_queue
from app.models.lead import Lead
from app.models.failed_job import FailedJob
from app.schemas.lead import LeadCreate
from app.tasks.lead_tasks import sync_lead_to_zoho_task


async def process_lead(
    db: Session,
    lead_data: LeadCreate,
    source: str,
    raw_payload: Optional[dict] = None
) -> Optional[Lead]:
    """
    Process an incoming lead: Dedup -> Store -> Enqueue CRM Sync.
    
    Args:
        db: Database session.
        lead_data: Mapped lead data in standard format.
        source: Source of the lead (housing, 99acres, website, etc.).
        raw_payload: Original data from the source for debugging.
        
    Returns:
        The created Lead object, or None if it was a duplicate.
    """
    try:
        # 1. Deduplication (Phone + Source)
        # We also check for external_id if provided by the source
        query = db.query(Lead).filter(Lead.phone == lead_data.phone, Lead.source == source)
        
        if lead_data.external_id:
            query = query.filter(Lead.external_id == lead_data.external_id)
            
        existing = query.first()
        if existing:
            logger.info(f"Duplicate lead skipped: {lead_data.phone} from {source}")
            return None

        # 2. Store in Database
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
            crm_status="pending"
        )
        
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)
        
        logger.success(f"New lead stored: ID={new_lead.id}, Phone={new_lead.phone}, Source={source}")

        # 3. Enqueue CRM Sync (Asynchronous)
        if lead_queue:
            try:
                lead_queue.enqueue(
                    sync_lead_to_zoho_task,
                    new_lead.id,
                    job_id=f"sync_zoho_{new_lead.id}"
                )
                new_lead.crm_status = "queued"
                db.commit()
                logger.info(f"Enqueued Zoho sync for lead {new_lead.id}")
            except Exception as enqueue_err:
                logger.error(f"Failed to enqueue lead {new_lead.id}: {enqueue_err}")
                new_lead.crm_status = "failed"
                db.commit()
        else:
            logger.warning("Redis Queue (lead_queue) not available. CRM sync will not happen automatically.")

        return new_lead

    except Exception as e:
        db.rollback()
        error_msg = f"Failed to process lead from {source}: {str(e)}"
        logger.error(error_msg)
        
        # Log to failed_jobs table for observability
        try:
            failed = FailedJob(
                job_name=f"process_lead_{source}",
                payload={"lead_data": lead_data.dict(), "raw_payload": raw_payload},
                error=str(e),
                stack_trace=traceback.format_exc()
            )
            db.add(failed)
            db.commit()
        except Exception as log_err:
            logger.error(f"Failed to record failed job: {log_err}")
            
        return None
