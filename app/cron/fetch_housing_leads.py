"""Background cron scheduler for Housing.com lead auto-sync.

Runs a background task every 2 minutes that:
1. Reads the last fetched timestamp from DB
2. Fetches new leads from Housing.com API
3. Processes them through the lead pipeline (DB → Zoho CRM → AI calling)
4. Updates the last fetched timestamp
"""

import asyncio
import os
import time
from datetime import datetime

from loguru import logger
from app.core.config import settings


async def _run_housing_sync():
    """Execute one Housing.com lead sync cycle."""
    from app.configs.db_config import MySQLSessionLocal
    from app.models.sync_metadata import SyncMetadata
    from app.services.housing_lead_service import housing_lead_service
    from app.utils.email_utils import email_service

    if not housing_lead_service.is_configured:
        logger.debug("Housing.com sync skipped — not configured")
        return

    db = MySQLSessionLocal()
    try:
        # Get or create sync metadata
        meta = db.query(SyncMetadata).filter(SyncMetadata.source == "housing").first()
        if not meta:
            meta = SyncMetadata(source="housing")
            db.add(meta)
            db.commit()
            db.refresh(meta)

        now = int(time.time())

        # Use last_lead_timestamp if available, otherwise default to 2 hours ago
        start_int = int(str(meta.last_lead_timestamp)) if meta.last_lead_timestamp is not None else (now - 7200)

        # Housing API strictly allows max 2 days difference.
        # If the gap > 47 hours, cap the end_date. Successive cron runs will catch up.
        end_int = now
        if end_int - start_int > 170000:
            end_int = start_int + 170000

        start_date = str(start_int)
        end_date = str(end_int)

        logger.info(
            f"Housing cron sync: start_date={start_date}, end_date={end_date}"
        )

        # Use a simple mock for background_tasks since we're in a cron context
        # The pipeline will still store leads in DB, but Zoho/AI calling
        # needs to be handled directly
        from unittest.mock import MagicMock

        from app.api.webhooks import _process_lead_pipeline
        from app.models.lead import Lead
        from app.schemas.lead import LeadCreate

        leads_raw, error = await housing_lead_service.fetch_leads(
            start_date, end_date
        )

        if error:
            logger.error(f"Housing cron sync error: {error}")
            # Alert only if we were previously healthy
            if meta.status != "error":
                asyncio.create_task(email_service.send_sync_error_alert("housing", f"API Error: {error}"))
            
            meta.status = "error"
            meta.last_error = f"API Error: {error}"
            db.commit()
            return

        imported: int = 0
        skipped: int = 0

        for raw_lead in leads_raw:
            mapped = housing_lead_service.map_lead(raw_lead)
            phone = mapped.get("phone", "")

            if not phone or len(phone) < 10:
                skipped += 1  # type: ignore[operator]
                continue

            # Deduplicate: phone + (external_id OR lead_date)
            query = db.query(Lead).filter(Lead.phone == phone, Lead.source == "housing")
            
            ext_id = mapped.get("external_id")
            o_date = mapped.get("lead_date")
            
            if ext_id and o_date:
                from sqlalchemy import or_
                query = query.filter(or_(Lead.external_id == ext_id, Lead.lead_date == o_date))
            elif ext_id:
                query = query.filter(Lead.external_id == ext_id)
            elif o_date:
                query = query.filter(Lead.lead_date == o_date)
                
            existing = query.first()
            if existing:
                skipped += 1  # type: ignore[operator]
                continue

            # Store in DB
            try:
                payload = LeadCreate(
                    name=mapped.get("name"),
                    phone=phone,
                    email=mapped.get("email"),
                    project_name=mapped.get("project_name"),
                    location=mapped.get("location"),
                    property_type=mapped.get("property_type"),
                    message=mapped.get("message"),
                    lead_date=mapped.get("lead_date"),
                    external_id=mapped.get("external_id"),
                )

                # Use a real background_tasks-like approach: process inline
                bg = MagicMock()
                zoho_tasks = []
                bg.add_task = lambda fn, *a, **kw: zoho_tasks.append((fn, a, kw))

                _process_lead_pipeline("housing", payload, bg, db)
                imported += 1  # type: ignore[operator]

                # Execute Zoho + AI tasks
                for fn, args, kwargs in zoho_tasks:
                    try:
                        if asyncio.iscoroutinefunction(fn):
                            await fn(*args, **kwargs)
                        else:
                            fn(*args, **kwargs)
                    except Exception as e:
                        logger.error(f"Background task error: {e}")

            except Exception as e:
                logger.error(f"Housing cron: failed to process lead phone={phone}: {e}")

        # Update sync metadata
        meta.last_lead_timestamp = end_date
        meta.last_sync_at = datetime.now()
        meta.leads_fetched = len(leads_raw)
        meta.leads_imported = imported
        meta.status = "active"
        meta.last_error = None
        db.commit()

        logger.info(
            f"Housing cron sync complete: fetched={len(leads_raw)}, "
            f"imported={imported}, skipped={skipped}"
        )

    except Exception as e:
        logger.error(f"Housing cron sync failed: {e}")
        
        # Log failure for observability
        try:
            from app.models.failed_job import FailedJob
            import traceback
            
            failed = FailedJob(
                job_name="sync_housing_job",
                error=str(e),
                stack_trace=traceback.format_exc()
            )
            db.add(failed)
            db.commit()
        except Exception as log_err:
            logger.error(f"Failed to log failed job: {log_err}")

        # Alert only if we were previously healthy
        if meta is not None and meta.status != "error":
            asyncio.create_task(email_service.send_sync_error_alert("housing", f"System Error: {str(e)}"))
            
        if meta is not None:
            meta.status = "error"
            meta.last_error = f"System Error: {str(e)}"
            db.commit()
        db.rollback()
    finally:
        db.close()


async def housing_cron_loop():
    """Infinite loop that runs the Housing.com sync every 2 minutes."""
    interval = settings.HOUSING_SYNC_INTERVAL_SECONDS
    logger.info(f"Housing.com cron started — syncing every {interval}s")

    # Wait 10 seconds after startup before first run
    await asyncio.sleep(10)

    while True:
        try:
            await _run_housing_sync()
        except Exception as e:
            logger.error(f"Housing cron loop error: {e}")

        await asyncio.sleep(interval)
