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
