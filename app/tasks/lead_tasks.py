"""RQ tasks for lead processing, CRM synchronisation, and contact notifications.

All functions in this module are executed by RQ workers outside the
FastAPI request cycle. Each task opens its own DB session.
"""

import asyncio
import traceback

from loguru import logger

from app.configs.db_config import MySQLSessionLocal
from app.events.event_service import publish_event
from app.models.failed_job import FailedJob
from app.repo import lead as lead_repo
from app.utils.zoho_adapter import CRMLeadAdapter
from app.utils.zoho_crm_service import zoho_crm_service

# ────────────────────────────────────────────────────────────────────
#  Constants
# ────────────────────────────────────────────────────────────────────
ZOHO_SYNC_TIMEOUT_SECONDS: float = 10.0
MAX_RETRIES: int = 5


# ────────────────────────────────────────────────────────────────────
#  Zoho CRM Sync Task
# ────────────────────────────────────────────────────────────────────
def sync_lead_to_zoho_task(lead_id: int) -> None:
    """RQ Task: Sync a stored lead to Zoho CRM using only its ID.

    Retry / DLQ behaviour is handled by RQ's built-in ``Retry`` (configured
    at enqueue time in ``lead_processor._enqueue_crm_sync``).  When all
    retries are exhausted the task falls through to the DLQ branch below.
    """
    logger.info(f"RQ Task: Syncing Lead #{lead_id} to Zoho CRM…")

    with MySQLSessionLocal() as session:
        lead_obj = lead_repo.get_lead_by_id(session, lead_id)
        if not lead_obj:
            logger.error(f"Lead #{lead_id} not found in database. Sync aborted.")
            return

        # ── 1. Idempotency check ──────────────────────────────────
        if lead_obj.zoho_synced and lead_obj.zoho_lead_id:
            logger.info(
                f"Lead #{lead_id} already synced to Zoho "
                f"({lead_obj.zoho_lead_id}). Skipping."
            )
            return

        # ── 2. Mark as processing ─────────────────────────────────
        lead_repo.update_lead(session, lead_obj, {"crm_status": "processing"})
        session.commit()
        publish_event(lead_id, "CRM_SYNC_STARTED", "Starting Zoho CRM synchronisation")

        try:
            # ── 3. Adapt and send ─────────────────────────────────
            adapter = CRMLeadAdapter(lead_obj, lead_obj.source)

            zoho_lead_id = asyncio.run(
                asyncio.wait_for(
                    zoho_crm_service.create_or_update_lead(adapter),
                    timeout=ZOHO_SYNC_TIMEOUT_SECONDS,
                )
            )

            if not zoho_lead_id:
                raise ValueError(
                    "Zoho CRM returned no lead ID (possible validation error)"
                )

            # ── 4. Success ────────────────────────────────────────
            logger.info(
                f"Lead #{lead_id} successfully synced to Zoho CRM: {zoho_lead_id}"
            )
            lead_repo.update_lead(
                session,
                lead_obj,
                {
                    "zoho_lead_id": zoho_lead_id,
                    "zoho_synced": True,
                    "crm_status": "success",
                },
            )
            session.commit()
            publish_event(
                lead_id,
                "CRM_SYNC_SUCCESS",
                f"Successfully synced to Zoho CRM: {zoho_lead_id}",
            )

        except Exception as e:
            _handle_sync_failure(session, lead_obj, lead_id, e)


def _handle_sync_failure(session, lead_obj, lead_id: int, error: Exception) -> None:
    """Handle CRM sync failure — retry or move to DLQ."""
    from rq import get_current_job

    job = get_current_job()

    if job and hasattr(job, "retries_left") and job.retries_left > 0:
        # RQ will automatically retry — just update status
        retry_num = MAX_RETRIES - job.retries_left + 1
        logger.warning(
            f"Sync attempt {retry_num}/{MAX_RETRIES} failed for "
            f"Lead #{lead_id}: {error}. Retrying…"
        )
        lead_repo.update_lead(session, lead_obj, {"crm_status": "retrying"})
        session.commit()
        publish_event(
            lead_id,
            "CRM_SYNC_RETRYING",
            f"Sync failed, retrying (attempt {retry_num})",
            payload=str(error),
        )
        raise  # Re-raise to trigger RQ retry

    # ── Dead Letter Queue: permanently failed ─────────────────
    logger.error(
        f"CRM Sync permanently failed for Lead #{lead_id} "
        f"after retries: {error}"
    )
    lead_repo.update_lead(
        session, lead_obj, {"crm_status": "permanently_failed"}
    )
    session.commit()
    publish_event(
        lead_id,
        "CRM_SYNC_FAILED",
        "Sync permanently failed after maximum retries",
        payload=str(error),
    )

    # Log to FailedJobs for visibility (Dead Letter Queue)
    try:
        failed = FailedJob(
            job_name=f"sync_zoho_{lead_id}",
            payload={"lead_id": lead_id},
            error=str(error),
            stack_trace=traceback.format_exc(),
        )
        session.add(failed)
        session.commit()
    except Exception as log_err:
        logger.error(f"Failed to record DLQ entry: {log_err}")


# ────────────────────────────────────────────────────────────────────
#  Contact Notification Task
# ────────────────────────────────────────────────────────────────────
def process_contact_notifications_task(
    contact_data_dict: dict, contact_id: int
) -> None:
    """RQ Task: Handle all post-creation notifications for a website contact."""
    logger.info(f"RQ Task: Processing notifications for Contact #{contact_id}…")

    from app.api.retell import trigger_outbound_call
    from app.repo import realty as realty_repo
    from app.utils.email_utils import email_service

    # Simple object to mimic Pydantic for the adapter
    class SimpleObj:
        def __init__(self, d: dict):
            for k, v in d.items():
                setattr(self, k, v)

    contact_obj = SimpleObj(contact_data_dict)

    async def _run_async_tasks():
        tasks = [
            email_service.send_contact_notification(contact_obj),
            zoho_crm_service.create_or_update_lead(
                CRMLeadAdapter(contact_obj, "website")
            ),
        ]

        # AI Call logic
        if not getattr(contact_obj, "is_ai_called", False):
            tasks.append(
                trigger_outbound_call(
                    name=getattr(contact_obj, "name_", "User"),
                    phone=getattr(contact_obj, "phone", ""),
                    location=getattr(contact_obj, "location", ""),
                    property_type=getattr(contact_obj, "property_type", ""),
                    message=getattr(contact_obj, "message", ""),
                )
            )
            tasks.append(zoho_crm_service.log_call(contact_obj))

        await asyncio.gather(*tasks, return_exceptions=True)

        # Update DB state
        with MySQLSessionLocal() as session:
            db_contact = realty_repo.get_contact_by_id(session, contact_id)
            if db_contact:
                realty_repo.update_contact(
                    session, db_contact, {"is_ai_called": True}
                )

    try:
        asyncio.run(_run_async_tasks())
        logger.info(f"RQ Task: Notifications complete for Contact #{contact_id}")
    except Exception as e:
        logger.error(f"RQ Task Error [process_contact_notifications_task]: {e}")
        raise

# ────────────────────────────────────────────────────────────────────
#  Historical Recovery Task
# ────────────────────────────────────────────────────────────────────
def sync_historical_housing_task(days: int = 5) -> None:
    """RQ Task: Fetch historical housing leads over X days."""
    logger.info(f"RQ Task: Starting historical sync for last {days} days")
    
    async def _run_sync():
        from datetime import datetime
        from app.configs.db_config import MySQLSessionLocal
        from app.services.housing_lead_service import housing_lead_service, BUILDER_API_URL, BROKER_API_URL
        from app.services.lead_processor import process_lead
        from app.schemas.lead import LeadCreate
        from app.core.redis import redis_conn
        
        db = MySQLSessionLocal()
        try:
            end_date = int(datetime.now().timestamp())
            start_date = end_date - (86400 * days)
            
            logger.info(f"Background Recovery: Fetching missing Housing.com leads from {start_date} to {end_date}")
            
            builder_leads, _ = await housing_lead_service.fetch_leads(str(start_date), str(end_date), api_url=BUILDER_API_URL)
            broker_leads, _  = await housing_lead_service.fetch_leads(str(start_date), str(end_date), api_url=BROKER_API_URL)
            
            all_raw = (builder_leads or []) + (broker_leads or [])
            logger.info(f"Background Recovery: Total leads fetched: {len(all_raw)}")
            
            imported = 0
            skipped = 0
            for raw_lead in all_raw:
                mapped = housing_lead_service.map_lead(raw_lead)
                phone = (mapped.get("phone") or "").strip()
                if len(phone) < 7:
                    skipped += 1
                    continue
                    
                try:
                    lead_data = LeadCreate(
                        name=mapped.get("name"),
                        phone=phone,
                        email=mapped.get("email"),
                        project_name=mapped.get("project_name"),
                        location=mapped.get("location"),
                        property_type=mapped.get("property_type"),
                        budget=mapped.get("budget"),
                        message=mapped.get("message"),
                        lead_date=mapped.get("lead_date"),
                        external_id=mapped.get("external_id"),
                    )
                    result = await process_lead(db, lead_data, source="housing", raw_payload=raw_lead)
                    if result:
                        imported += 1
                    else:
                        skipped += 1
                except Exception as e:
                    logger.error(f"Lead process error: {e}")
                    skipped += 1
                    
            logger.info(f"Historical Recovery Complete: Imported {imported}, Skipped {skipped}")
            
        finally:
            db.close()
            # Release lock
            if redis_conn:
                redis_conn.delete("lock:historical_sync_housing")

    try:
        asyncio.run(_run_sync())
    except Exception as e:
        logger.error(f"Historical Sync Task Failed: {e}")
        from app.core.redis import redis_conn
        if redis_conn:
            redis_conn.delete("lock:historical_sync_housing")
        raise
