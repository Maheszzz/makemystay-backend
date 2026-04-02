"""RQ tasks for lead processing, CRM synchronisation, and contact notifications.

All functions in this module are executed by RQ workers outside the
FastAPI request cycle. Each task opens its own DB session.
"""

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Optional, Sequence, Union

from celery.exceptions import Retry
from loguru import logger

from app.configs.db_config import MySQLSessionLocal
from app.core.celery_app import celery_app
from app.events.event_service import publish_event
from app.models.failed_job import FailedJob
from app.repo import lead as lead_repo
from app.models.failed_zoho_task import FailedZohoTask
from app.services.zoho_circuit import ZohoCircuitOpenError
from app.services.zoho_daily_budget import ZohoDailyBudgetExceeded
from app.services.zoho_sync_policy import (
    should_defer_due_to_concurrent_processing,
    should_skip_recent_successful_sync,
)
from app.utils.zoho_adapter import CRMLeadAdapter
from app.utils.zoho_crm_service import ZohoCRMError, ZohoRateLimitError, zoho_crm_service

# ────────────────────────────────────────────────────────────────────
#  Constants
# ────────────────────────────────────────────────────────────────────
ZOHO_SYNC_TIMEOUT_SECONDS: float = 10.0
MAX_RETRIES: int = 5


# ────────────────────────────────────────────────────────────────────
#  Celery queue monitoring (Beat — optional)
# ────────────────────────────────────────────────────────────────────
@celery_app.task(name="monitor_celery_queue_backlog")
def monitor_celery_queue_backlog() -> None:
    """Emit error logs when default queue depth exceeds ``CELERY_QUEUE_BACKLOG_ALERT_THRESHOLD``."""
    from app.services.celery_queue_monitor import log_celery_queue_backlog_if_high

    log_celery_queue_backlog_if_high()


@celery_app.task(name="log_zoho_budget_usage_metric")
def log_zoho_budget_usage_metric() -> None:
    """Periodic ``Zoho Budget Usage | used=… | remaining=…`` for log-based trending."""
    from app.services.zoho_daily_budget import log_budget_usage_metric

    log_budget_usage_metric()


# ────────────────────────────────────────────────────────────────────
#  Zoho CRM Sync Task
# ────────────────────────────────────────────────────────────────────
@celery_app.task(name="sync_lead_to_zoho_task", bind=True, max_retries=5, default_retry_delay=60)
def sync_lead_to_zoho_task(self, lead_id: int) -> None:
    """Celery Task: Sync a stored lead to Zoho CRM using only its ID.

    Uses ``SELECT FOR UPDATE`` to serialize concurrent workers, idempotency for duplicate
    task delivery, and structured logging for production debugging.
    """
    logger.info(f"Celery Task: Syncing Lead #{lead_id} to Zoho CRM...")

    now = datetime.now(timezone.utc)

    session = MySQLSessionLocal()
    try:
        lead_obj = lead_repo.get_lead_by_id_for_update(session, lead_id)
        if not lead_obj:
            logger.error(f"Lead #{lead_id} not found in database. Sync aborted.")
            return

        if should_skip_recent_successful_sync(lead_obj, now):
            logger.info(
                f"Zoho Sync | lead_id={lead_id} | zoho_id={lead_obj.zoho_lead_id} | skipped=duplicate_task_recent_success"
            )
            return

        if lead_obj.crm_status == "processing":
            if should_defer_due_to_concurrent_processing(lead_obj, now):
                session.rollback()
                raise self.retry(countdown=30)
            logger.warning(
                f"Zoho Sync takeover | lead_id={lead_id} | reason=stale_processing"
            )

        lead_repo.update_lead(session, lead_obj, {"crm_status": "processing"})
        session.commit()
        publish_event(lead_id, "CRM_SYNC_STARTED", "Starting Zoho CRM synchronisation")
    finally:
        session.close()

    session2 = MySQLSessionLocal()
    try:
        lead_obj = lead_repo.get_lead_by_id(session2, lead_id)
        if not lead_obj:
            return

        if lead_obj.assigned_employee and lead_obj.assigned_employee.zoho_user_id:
            setattr(lead_obj, "owner_zoho_id", lead_obj.assigned_employee.zoho_user_id)
        else:
            setattr(lead_obj, "owner_zoho_id", None)

        adapter = CRMLeadAdapter(lead_obj, lead_obj.source)
        action = "update" if lead_obj.zoho_lead_id else "create"
        logger.info(
            f"Zoho Sync | lead_id={lead_id} | zoho_id={lead_obj.zoho_lead_id or '-'} | action={action}"
        )

        try:
            zoho_lead_id = asyncio.run(
                asyncio.wait_for(
                    zoho_crm_service.create_or_update_lead(adapter),
                    timeout=ZOHO_SYNC_TIMEOUT_SECONDS,
                )
            )
        except ZohoDailyBudgetExceeded as e:
            lead_locked = lead_repo.get_lead_by_id_for_update(session2, lead_id)
            if lead_locked:
                lead_repo.update_lead(session2, lead_locked, {"crm_status": "queued"})
                session2.commit()
            logger.warning(
                f"Zoho Sync | lead_id={lead_id} | skipped=daily_budget_soft_limit | retry_in_1h"
            )
            raise self.retry(exc=e, countdown=3600)

        lead_locked = lead_repo.get_lead_by_id_for_update(session2, lead_id)
        if not lead_locked:
            return

        logger.info(
            f"Zoho Sync | lead_id={lead_id} | zoho_id={zoho_lead_id} | result=success"
        )
        lead_repo.update_lead(
            session2,
            lead_locked,
            {
                "zoho_lead_id": zoho_lead_id,
                "zoho_synced": True,
                "crm_status": "success",
                "last_zoho_sync_at": datetime.now(timezone.utc),
            },
        )
        session2.commit()
        publish_event(
            lead_id,
            "CRM_SYNC_SUCCESS",
            f"Successfully synced to Zoho CRM: {zoho_lead_id}",
        )

    except Retry:
        raise
    except Exception as e:
        if isinstance(e, ZohoDailyBudgetExceeded):
            raise
        if self.request.retries < self.max_retries:
            retry_num = self.request.retries + 1
            logger.warning(
                f"Zoho Sync | lead_id={lead_id} | attempt={retry_num}/{self.max_retries} | error={e}"
            )
            try:
                lead_locked = lead_repo.get_lead_by_id_for_update(session2, lead_id)
                if lead_locked:
                    lead_repo.update_lead(session2, lead_locked, {"crm_status": "retrying"})
                    session2.commit()
                publish_event(
                    lead_id,
                    "CRM_SYNC_RETRYING",
                    f"Sync failed, retrying (attempt {retry_num})",
                    payload=str(e),
                )
            except Exception as inner:
                logger.error(f"Failed to mark lead {lead_id} retrying: {inner}")

            countdown = 60
            if isinstance(e, ZohoRateLimitError):
                countdown = 300
                logger.warning(f"Zoho Sync | lead_id={lead_id} | rate_limited | retry_in_5m")
            elif isinstance(e, ZohoCircuitOpenError):
                countdown = 300
                logger.warning(f"Zoho Sync | lead_id={lead_id} | circuit_open | retry_in_5m")

            raise self.retry(exc=e, countdown=countdown)

        logger.error(
            f"Zoho Sync | lead_id={lead_id} | result=permanently_failed | error={e}"
        )
        try:
            lead_locked = lead_repo.get_lead_by_id_for_update(session2, lead_id)
            if lead_locked:
                lead_repo.update_lead(session2, lead_locked, {"crm_status": "permanently_failed"})
                session2.commit()
            publish_event(
                lead_id,
                "CRM_SYNC_FAILED",
                "Sync permanently failed after maximum retries",
                payload=str(e),
            )
            try:
                from app.utils.alerting import notify_admin_critical_failure

                notify_admin_critical_failure(
                    subject=f"Zoho Sync Permanent Failure: Lead #{lead_id}",
                    message=f"Sync failed after {self.max_retries} retries due to: {e}",
                    context={"lead_id": lead_id, "error": str(e)},
                )

                failed = FailedJob(
                    job_name=f"sync_zoho_{lead_id}",
                    payload={"lead_id": lead_id},
                    error=str(e),
                    stack_trace=traceback.format_exc(),
                )
                session2.add(failed)
                session2.add(
                    FailedZohoTask(
                        lead_id=lead_id,
                        error=str(e),
                        payload={"lead_id": lead_id},
                    )
                )
                session2.commit()
            except Exception as log_err:
                logger.error(f"Failed to record DLQ entry: {log_err}")
        except Exception as final_err:
            logger.error(f"Zoho Sync DLQ handling failed for lead {lead_id}: {final_err}")
    finally:
        session2.close()


@celery_app.task(name="sync_contact_to_zoho_task", bind=True, max_retries=5, default_retry_delay=60)
def sync_contact_to_zoho_task(self, contact_id: int) -> None:
    """Celery Task: Sync a contact to Zoho CRM using only its ID."""
    logger.info(f"Celery Task: Syncing Contact #{contact_id} to Zoho CRM...")

    from app.repo import realty as realty_repo
    with MySQLSessionLocal() as session:
        contact_obj = realty_repo.get_contact_by_id(session, contact_id)
        if not contact_obj:
            logger.error(f"Contact #{contact_id} not found. Sync aborted.")
            return

        try:
            adapter = CRMLeadAdapter(contact_obj, "website")
            logger.info(f"Zoho Sync | contact_id={contact_id} | action=upsert")
            zoho_id = asyncio.run(
                asyncio.wait_for(
                    zoho_crm_service.create_or_update_lead(adapter),
                    timeout=ZOHO_SYNC_TIMEOUT_SECONDS,
                )
            )
            logger.info(f"Contact #{contact_id} successfully synced to Zoho: {zoho_id}")
        except Exception as e:
            logger.error(f"Contact sync failed: {e}")
            if self.request.retries < self.max_retries:
                countdown = 300 if isinstance(e, ZohoRateLimitError) else 60
                raise self.retry(exc=e, countdown=countdown)


# ────────────────────────────────────────────────────────────────────
#  Contact Notification Task
# ────────────────────────────────────────────────────────────────────
@celery_app.task(name="process_contact_notifications_task")
def process_contact_notifications_task(
    contact_data_dict: dict, contact_id: int
) -> None:
    """Celery Task: Handle all post-creation notifications for a website contact."""
    logger.info(f"Celery Task: Processing notifications for Contact #{contact_id}...")

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

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                task_name = "Unknown"
                if i == 0: task_name = "Email Notification"
                elif i == 1: task_name = "Zoho CRM Sync"
                elif i == 2: task_name = "Retell AI Call Trigger"
                elif i == 3: task_name = "Zoho Call Logging"
                logger.error(f"Post-creation task '{task_name}' failed for Contact #{contact_id}: {res}")

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
@celery_app.task(name="sync_historical_housing_task")
def sync_historical_housing_task(days: int = 5) -> None:
    """Celery Task: Fetch historical housing leads over X days."""
    from app.core.redis import HISTORICAL_HOUSING_SYNC_LOCK, redis_conn

    logger.info(f"Celery Task: Starting historical sync for last {days} days")

    async def _run_sync():
        from datetime import datetime, timezone
        from app.configs.db_config import MySQLSessionLocal
        from app.services.housing_lead_service import housing_lead_service, BUILDER_API_URL, BROKER_API_URL
        from app.services.lead_processor import process_lead
        from app.schemas.lead import LeadCreate

        db = MySQLSessionLocal()
        try:
            end_date = int(datetime.now(timezone.utc).timestamp())
            start_date = end_date - (86400 * days)

            logger.info(f"Background Recovery: Fetching missing Housing.com leads from {start_date} to {end_date}")

            builder_leads, _ = await housing_lead_service.fetch_leads(str(start_date), str(end_date), api_url=BUILDER_API_URL)
            broker_leads, _ = await housing_lead_service.fetch_leads(str(start_date), str(end_date), api_url=BROKER_API_URL)

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

    try:
        asyncio.run(_run_sync())
    except Exception as e:
        logger.error(f"Historical Sync Task Failed: {e}")
        raise
    finally:
        if redis_conn:
            try:
                redis_conn.delete(HISTORICAL_HOUSING_SYNC_LOCK)
            except Exception as ex:
                logger.warning(f"Failed to release historical housing sync lock: {ex}")

# ────────────────────────────────────────────────────────────────────
#  AI Call Trigger Task
# ────────────────────────────────────────────────────────────────────
@celery_app.task(name="enqueue_call_task", bind=True, max_retries=3, default_retry_delay=30)
def enqueue_call_task(self, contact_id: int, phone: str, name: str) -> None:
    """Celery Task: Trigger an outbound AI call for a new website contact."""
    logger.info(f"Celery Task: Enqueuing AI call for Contact #{contact_id}...")
    
    from app.models.retell_call import RetellCall
    from app.api.retell import trigger_outbound_call

    with MySQLSessionLocal() as session:
        # Create tracking row directly. Since we don't query Contact, we save a read query.
        call_log = RetellCall(
            contact_id=contact_id,
            to_phone=phone,
            status="queued"
        )
        session.add(call_log)
        session.commit()
        session.refresh(call_log)
        
        try:
            data = asyncio.run(trigger_outbound_call(
                name=name or "User",
                phone=phone,
                location="",
                property_type="",
                message="interested in property options",
                test_id=call_log.id,
                contact_id=contact_id
            ))
            
            if data and (data.get("call_id") or data.get("id")):
                call_id = data.get("call_id") or data.get("id")
                call_log.retell_call_id = call_id
                call_log.status = "calling"
                session.commit()
                logger.success(f"Successfully triggered AI call {call_id} for Contact #{contact_id}")
            else:
                call_log.status = "failed"
                session.commit()
                logger.error(f"Failed to trigger AI call for Contact #{contact_id}: No call_id from Retell")
                
        except Exception as e:
            call_log.status = "failed"
            session.commit()
            logger.error(f"Error triggering AI call for Contact #{contact_id}: {e}")
            raise self.retry(exc=e)
@celery_app.task(name="process_csv_import_task", bind=True, max_retries=1)
def process_csv_import_task(self, import_id: int, csv_text: str, source: str) -> None:
    """Celery Task: Process a CSV lead import asynchronously."""
    logger.info(f"Celery Task: Starting CSV Import #{import_id}...")

    from app.services.csv_lead_import import run_csv_import
    from app.models.csv_import import CsvImport

    with MySQLSessionLocal() as session:
        imp = session.query(CsvImport).filter(CsvImport.id == import_id).first()
        if not imp:
            logger.error(f"CsvImport #{import_id} not found.")
            return

        try:
            asyncio.run(
                run_csv_import(
                    db=session,
                    text=csv_text,
                    source=source,
                    import_id=import_id,
                    dry_run=False,
                )
            )
            logger.success(f"Celery Task: CSV Import #{import_id} finished processing.")
        except Exception as e:
            logger.error(f"Celery Task: CSV Import #{import_id} failed: {e}")
            imp.status = "failed"
            session.commit()
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)
            raise


@celery_app.task(name="retry_csv_import_failures_task", bind=True, max_retries=5, default_retry_delay=120)
def retry_csv_import_failures_task(self, import_id: int) -> None:
    """Re-process rows in ``csv_import_failures`` for an import (admin-triggered)."""
    from app.services.csv_lead_import import retry_csv_import_failed_rows
    from app.models.csv_import import CsvImport

    logger.info(f"Celery Task: Retrying failed CSV rows for import #{import_id}...")
    with MySQLSessionLocal() as session:
        imp = session.query(CsvImport).filter(CsvImport.id == import_id).first()
        if not imp:
            logger.error(f"CsvImport #{import_id} not found.")
            return
        try:
            asyncio.run(retry_csv_import_failed_rows(session, import_id))
            logger.success(f"Celery Task: Retry finished for import #{import_id}.")
        except Exception as e:
            logger.error(f"Celery Task: Retry failed for import #{import_id}: {e}")
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)
            raise


# ────────────────────────────────────────────────────────────────────
#  WhatsApp Notification Task
# ────────────────────────────────────────────────────────────────────
@celery_app.task(name="send_lead_whatsapp_task", bind=True, max_retries=3, default_retry_delay=60)
def send_lead_whatsapp_task(self, lead_id: int, template_sid: Optional[str] = None) -> None:
    """Celery Task: Send a WhatsApp message to a lead."""
    from app.services.whatsapp_service import send_template_whatsapp
    from app.core.config import settings

    logger.info(f"Celery Task: Sending WhatsApp to Lead #{lead_id}...")
    with MySQLSessionLocal() as session:
        lead_obj = lead_repo.get_lead_by_id(session, lead_id)
        if not lead_obj or not lead_obj.phone:
            logger.error(f"Lead #{lead_id} not found or has no phone. WhatsApp aborted.")
            return

        sid = template_sid or settings.TWILIO_WHATSAPP_LEAD_TEMPLATE
        if not sid:
            logger.error("No WhatsApp template SID configured.")
            return

        try:
            # Prepare template variables
            variables = {
                "1": lead_obj.name or "User",
                "2": lead_obj.project_name or "our project",
            }
            
            result = send_template_whatsapp(
                to=lead_obj.phone,
                content_sid=sid,
                content_variables=variables
            )
            
            if result.ok:
                logger.success(f"WhatsApp sent successfully to Lead #{lead_id} (SID: {result.sid})")
                publish_event(lead_id, "WHATSAPP_SENT", f"WhatsApp sent via {sid}")
            else:
                raise ValueError(result.error)

        except Exception as e:
            logger.error(f"WhatsApp failed for Lead #{lead_id}: {e}")
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)


# ────────────────────────────────────────────────────────────────────
#  AI Call Task for Leads
# ────────────────────────────────────────────────────────────────────
@celery_app.task(name="trigger_lead_ai_call_task", bind=True, max_retries=2, default_retry_delay=120)
def trigger_lead_ai_call_task(self, lead_id: int) -> None:
    """Celery Task: Trigger an outbound AI call for a lead."""
    from app.api.retell import trigger_outbound_call
    from app.models.retell_call import RetellCall

    logger.info(f"Celery Task: Triggering AI call for Lead #{lead_id}...")
    with MySQLSessionLocal() as session:
        lead_obj = lead_repo.get_lead_by_id(session, lead_id)
        if not lead_obj or not lead_obj.phone:
            return

        # Check if already called or has a pending call
        existing_call = session.query(RetellCall).filter(
            RetellCall.lead_id == lead_id,
            RetellCall.status.in_(["queued", "calling", "completed"])
        ).first()
        
        if existing_call:
            logger.info(f"Lead #{lead_id} already has a call record (status: {existing_call.status}). Skipping.")
            return

        call_log = RetellCall(
            lead_id=lead_id,
            to_phone=lead_obj.phone,
            status="queued"
        )
        session.add(call_log)
        session.commit()
        session.refresh(call_log)

        try:
            data = asyncio.run(trigger_outbound_call(
                name=lead_obj.name or "User",
                phone=lead_obj.phone,
                location=lead_obj.location or "",
                project=lead_obj.project_name or "",
                lead_id=lead_id,
                test_id=call_log.id
            ))
            
            if data and (data.get("call_id") or data.get("id")):
                call_id = data.get("call_id") or data.get("id")
                call_log.retell_call_id = call_id
                call_log.status = "calling"
                session.commit()
                publish_event(lead_id, "AI_CALL_TRIGGERED", f"AI call triggered (ID: {call_id})")
            else:
                call_log.status = "failed"
                session.commit()
                logger.error(f"Failed to trigger AI call for Lead #{lead_id}: No ID from provider")

        except Exception as e:
            call_log.status = "failed"
            session.commit()
            logger.error(f"Error triggering AI call for Lead #{lead_id}: {e}")
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)
