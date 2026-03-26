"""Persistence for failed webhook ingestion rows."""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.failed_webhook_lead import FailedWebhookLead

_MAX_PAYLOAD = 60_000


def record_failed_webhook_lead(
    db: Session,
    *,
    source: str,
    external_ref: Optional[str],
    payload: str,
    error: str,
) -> FailedWebhookLead:
    body = payload if len(payload) <= _MAX_PAYLOAD else payload[:_MAX_PAYLOAD] + "\n…[truncated]"
    row = FailedWebhookLead(
        source=source,
        external_ref=(external_ref[:200] if external_ref else None),
        payload=body,
        error=error[:2000],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_unprocessed(db: Session, limit: int = 500) -> List[FailedWebhookLead]:
    return (
        db.query(FailedWebhookLead)
        .filter(FailedWebhookLead.processed_at.is_(None))
        .order_by(FailedWebhookLead.id.asc())
        .limit(limit)
        .all()
    )


def mark_processed(db: Session, row_id: int) -> None:
    row = db.query(FailedWebhookLead).filter(FailedWebhookLead.id == row_id).first()
    if row:
        row.processed_at = datetime.now(timezone.utc)
        db.commit()
