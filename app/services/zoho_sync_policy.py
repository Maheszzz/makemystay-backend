"""Rules for Celery Zoho sync: idempotency and concurrent workers.

Pass ``now=datetime.now(timezone.utc)`` from callers so cooldown windows stay consistent; use NTP on servers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings
from app.models.lead import Lead


def _ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def should_skip_recent_successful_sync(lead: Lead, now: datetime) -> bool:
    """Duplicate Celery delivery: skip extra API calls if we just succeeded."""
    if not (lead.zoho_synced and lead.zoho_lead_id and lead.last_zoho_sync_at):
        return False
    if lead.crm_status != "success":
        return False
    window = int(getattr(settings, "ZOHO_SYNC_IDEMPOTENCY_SECONDS", 120) or 120)
    last = _ensure_utc(lead.last_zoho_sync_at)
    if not last:
        return False
    age = (now - last).total_seconds()
    return 0 <= age < window


def should_defer_due_to_concurrent_processing(lead: Lead, now: datetime) -> bool:
    """Another worker holds ``processing`` and row is fresh — defer with Celery retry.

    If stuck in ``processing`` longer than ``ZOHO_PROCESSING_STALE_SECONDS``, returns False so
    this task can take over (worker crash / lost task).
    """
    if lead.crm_status != "processing":
        return False
    stale_after = float(getattr(settings, "ZOHO_PROCESSING_STALE_SECONDS", 300) or 300)
    updated = _ensure_utc(lead.updated_at) or _ensure_utc(lead.created_at)
    if not updated:
        return True
    age = (now - updated).total_seconds()
    if age >= stale_after:
        return False
    return True
