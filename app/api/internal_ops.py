"""Internal ops / metrics (protect with ``INTERNAL_METRICS_TOKEN``)."""

from __future__ import annotations

import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.models.failed_zoho_task import FailedZohoTask
from app.services.celery_queue_monitor import get_celery_queue_depth
from app.services.zoho_circuit import circuit_open_until_ts
from app.services.zoho_daily_budget import get_today_zoho_api_count

router = APIRouter(prefix="/internal", tags=["Internal"], include_in_schema=False)


def verify_internal_token(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    tok = (getattr(settings, "INTERNAL_METRICS_TOKEN", None) or "").strip()
    if not tok:
        raise HTTPException(status_code=404, detail="Not found")
    if (x_internal_token or "").strip() != tok:
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.get("/zoho-status")
def get_zoho_status(
    _: None = Depends(verify_internal_token),
    db: Session = Depends(get_mysql_db),
) -> dict[str, Any]:
    """Budget, queue depth, DLQ size, circuit state — for dashboards and on-call."""
    budget = int(getattr(settings, "ZOHO_DAILY_API_BUDGET", 0) or 0)
    ratio = float(getattr(settings, "ZOHO_DAILY_API_SOFT_LIMIT_RATIO", 0.8) or 0.8)
    soft = max(1, int(budget * ratio)) if budget > 0 else 0

    used = get_today_zoho_api_count()
    if used is None:
        used = -1

    qd = get_celery_queue_depth()
    if qd is None:
        qd = -1

    dlq_count = db.query(FailedZohoTask).count()
    threshold = int(getattr(settings, "CELERY_QUEUE_BACKLOG_ALERT_THRESHOLD", 1000) or 1000)

    until = circuit_open_until_ts()
    circuit_open = bool(until and time.time() < (until or 0))

    status = "healthy"
    if circuit_open:
        status = "degraded"
    elif qd != -1 and threshold > 0 and qd > threshold:
        status = "degraded"
    elif budget > 0 and used != -1 and soft > 0 and used >= soft:
        status = "degraded"

    return {
        "api_used": used,
        "budget": budget,
        "soft_threshold": soft,
        "queue_depth": qd,
        "dlq_count": dlq_count,
        "circuit_open": circuit_open,
        "status": status,
    }


@router.post("/zoho-dlq/reprocess/{lead_id}")
def reprocess_zoho_lead(
    lead_id: int,
    _: None = Depends(verify_internal_token),
) -> dict[str, Any]:
    """Re-enqueue a lead for Zoho sync (after fixing data or Zoho outage)."""
    from app.tasks.lead_tasks import sync_lead_to_zoho_task

    sync_lead_to_zoho_task.delay(lead_id)
    return {"ok": True, "lead_id": lead_id}
