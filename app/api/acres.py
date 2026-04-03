"""Admin-facing endpoints for 99acres lead sync.

Allows admins to manually trigger a lead pull from 99acres' private
Fetch Leads API and check the status of the last sync (from DB).
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
from app.services.acres_lead_service import acres_lead_service

acres_router = APIRouter(tags=["99acres Integration"])


@acres_router.post(
    "/99acres/sync-leads",
    summary="Sync leads from 99acres",
)
async def sync_99acres_leads_endpoint(
    start_date: Optional[str] = Query(
        None,
        description="Start date as epoch string. Defaults to last_lead_timestamp or 24h ago.",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date as epoch string. Defaults to now.",
    ),
    full_sync: bool = Query(
        False,
        description="If true, fetches from the beginning of time (epoch 0).",
    ),
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Trigger a manual lead sync from 99acres.

    - Uses last_lead_timestamp from DB as start_date if not provided
    - Deduplicates against existing leads in the database
    - New leads → MySQL → Zoho CRM → AI calling (all via background tasks)
    - Requires ACRES_API_KEY to be configured; otherwise returns a config error.
    """
    now = int(time.time())

    # Read last sync metadata
    meta = db.query(SyncMetadata).filter(SyncMetadata.source == "99acres").first()

    if full_sync:
        start_date = "0"
    elif not start_date:
        if meta and meta.last_lead_timestamp is not None:
            start_date = str(meta.last_lead_timestamp)
        else:
            start_date = str(now - 86400)  # default: last 24 hours

    if not end_date:
        end_date = str(now)

    logger.info(
        f"Admin triggered 99acres sync: "
        f"start_date={start_date}, end_date={end_date}"
    )

    result = await acres_lead_service.sync_leads(
        from_date=start_date,
        to_date=end_date,
        db=db,
    )

    # Persist sync metadata
    if not meta:
        meta = SyncMetadata(source="99acres")
        db.add(meta)

    meta.last_lead_timestamp = end_date
    meta.last_sync_at = datetime.now()
    meta.leads_fetched = result.get("fetched", 0)
    meta.leads_imported = result.get("imported", 0)
    meta.status = result.get("status", "active")
    if result.get("status") == "error":
        meta.last_error = result.get("error")
    else:
        meta.last_error = None
    db.commit()

    return result


@acres_router.get(
    "/99acres/sync-leads/status",
    summary="Get 99acres sync status",
)
def get_99acres_sync_status(
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Returns the status of the last 99acres lead sync from the database.
    Reports whether the pull API is configured and the last sync metadata.
    """
    meta = db.query(SyncMetadata).filter(SyncMetadata.source == "99acres").first()

    return {
        "is_configured": acres_lead_service.is_configured,
        "api_url": acres_lead_service.api_url,
        "last_lead_timestamp": meta.last_lead_timestamp if meta else None,
        "last_sync_at": (meta.last_sync_at or datetime.now()).isoformat() if meta else None,
        "leads_fetched": meta.leads_fetched if meta else 0,
        "leads_imported": meta.leads_imported if meta else 0,
        "status": meta.status if meta else "never_synced",
        "last_error": meta.last_error if meta else None,
    }
