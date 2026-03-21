"""Admin-facing endpoints for Housing.com lead sync.

Allows admins to manually trigger a lead pull from Housing.com's Pahal API
and check the status of the last sync (persisted in DB).
"""

import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from loguru import logger
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.models.sync_metadata import SyncMetadata
from app.services.housing_lead_service import (
    BROKER_API_URL,
    BUILDER_API_URL,
    housing_lead_service,
)

housing_router = APIRouter(tags=["Housing.com Integration"])


@housing_router.post(
    "/housing/sync-leads",
    summary="Sync leads from Housing.com",
)
async def sync_housing_leads(
    start_date: Optional[str] = Query(
        None,
        description="Start date as epoch string. Defaults to last_lead_timestamp or 24h ago.",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date as epoch string. Defaults to now.",
    ),
    lead_type: Optional[str] = Query(
        "builder",
        description="Type of leads to fetch: 'builder' or 'broker'",
    ),
    full_sync: bool = Query(
        False,
        description="If true, fetches from the beginning of time (epoch 0).",
    ),
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Trigger a manual lead sync from Housing.com.

    - Uses last_lead_timestamp from DB as start_date if not provided
    - Deduplicates against existing leads in the database
    - New leads → MySQL → Zoho CRM → AI calling (all via background tasks)
    """
    now = int(time.time())

    # Read last sync metadata
    meta = db.query(SyncMetadata).filter(SyncMetadata.source == "housing").first()

    if full_sync:
        start_date = "0"
    elif not start_date:
        if meta and meta.last_lead_timestamp is not None:
            start_date = str(meta.last_lead_timestamp)
        else:
            start_date = str(now - 86400)  # 24 hours ago

    if not end_date:
        end_date = str(now)

    api_url = BROKER_API_URL if lead_type == "broker" else BUILDER_API_URL

    logger.info(
        f"Admin triggered Housing.com sync: "
        f"start_date={start_date}, end_date={end_date}, type={lead_type}"
    )

    result = await housing_lead_service.sync_leads(
        start_date=start_date,
        end_date=end_date,
        db=db,
        api_url=api_url,
    )

    # Persist sync metadata
    if not meta:
        meta = SyncMetadata(source="housing")
        db.add(meta)

    meta.last_lead_timestamp = end_date
    meta.last_sync_at = datetime.now()
    meta.leads_fetched = result.get("fetched", 0)
    meta.leads_imported = result.get("imported", 0)
    db.commit()

    return result


@housing_router.get(
    "/housing/sync-leads/status",
    summary="Get Housing.com sync status",
)
def get_sync_status(
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Returns the status of the last Housing.com lead sync from the database.
    """
    meta = db.query(SyncMetadata).filter(SyncMetadata.source == "housing").first()

    return {
        "is_configured": housing_lead_service.is_configured,
        "last_lead_timestamp": meta.last_lead_timestamp if meta else None,
        "last_sync_at": (meta.last_sync_at or datetime.now()).isoformat() if meta else None,
        "leads_fetched": meta.leads_fetched if meta else 0,
        "leads_imported": meta.leads_imported if meta else 0,
    }
