"""Unified sync service for all lead sources.

This module coordinates fetching leads from pull-based APIs (Housing.com, 99acres, etc.)
and processing them through the centralized lead pipeline.
"""

import asyncio
import time
from datetime import datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.configs.db_config import MySQLSessionLocal
from app.models.sync_metadata import SyncMetadata
from app.schemas.lead import LeadCreate
from app.services.housing_lead_service import housing_lead_service
from app.services.lead_processor import process_lead


async def sync_all_sources():
    """Execute sync for all active lead sources."""
    db = MySQLSessionLocal()
    try:
        await asyncio.gather(
            sync_housing_leads(db),
            sync_99acres_leads(db)
        )
    except Exception as e:
        logger.error(f"Unified sync failed: {e}")
    finally:
        db.close()


async def sync_housing_leads(db: Session):
    """Fetch and process leads from Housing.com."""
    if not housing_lead_service.is_configured:
        logger.debug("Housing.com sync skipped — not configured")
        return

    try:
        # Get or create sync metadata
        meta = db.query(SyncMetadata).filter(SyncMetadata.source == "housing").first()
        if not meta:
            meta = SyncMetadata(source="housing")
            db.add(meta)
            db.commit()
            db.refresh(meta)

        now = int(time.time())
        # Default to 24 hours ago if no previous timestamp
        start_int = int(str(meta.last_lead_timestamp)) if meta.last_lead_timestamp else (now - 86400)

        # Housing API strictly allows max 2 days difference.
        # Cap at 47 hours to stay safe.
        end_int = now
        if end_int - start_int > 170000:
            end_int = start_int + 170000

        start_date = str(start_int)
        end_date = str(end_int)

        logger.info(f"Syncing Housing leads: {start_date} to {end_date}")
        leads_raw, error = await housing_lead_service.fetch_leads(start_date, end_date)

        if error:
            logger.error(f"Housing sync error: {error}")
            meta.status = "error"
            meta.last_error = error
            db.commit()
            return

        imported = 0
        for raw_lead in leads_raw:
            mapped = housing_lead_service.map_lead(raw_lead)
            lead_data = LeadCreate(
                name=mapped.get("name"),
                phone=mapped.get("phone", ""),
                email=mapped.get("email"),
                project_name=mapped.get("project_name"),
                location=mapped.get("location"),
                property_type=mapped.get("property_type"),
                message=mapped.get("message"),
                lead_date=mapped.get("lead_date"),
                external_id=mapped.get("external_id"),
            )

            result = await process_lead(db, lead_data, source="housing", raw_payload=raw_lead)
            if result:
                imported += 1

        # Update metadata — only moves forward if fetch_leads above succeeded
        meta.last_lead_timestamp = end_date
        meta.last_sync_at = datetime.now()
        meta.leads_fetched = len(leads_raw)
        meta.leads_imported = imported
        meta.status = "active"
        meta.last_error = None
        db.commit()

        logger.success(f"Housing sync complete: {len(leads_raw)} fetched, {imported} imported")

    except Exception as e:
        logger.error(f"Housing sync task failed: {e}")
        db.rollback()


async def sync_99acres_leads(db: Session):
    """
    Fetch and process leads from 99acres.
    Currently a stub as 99acres primarily uses webhooks.
    """
    # Logic for 99acres pull-based API will go here if/when available
    logger.debug("99acres pull-based sync skipped — no active pull API configured")
    await asyncio.sleep(0.1)
