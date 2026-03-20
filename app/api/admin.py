
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.redis import lead_queue, redis_conn
from app.models.lead import Lead
from app.models.sync_metadata import SyncMetadata
from app.tasks.lead_tasks import sync_lead_to_zoho_task
from app.schemas.whatsapp import WhatsAppBulkSendRequest, WhatsAppBulkSendResponse
from app.core.config import settings
from app.tasks.whatsapp_tasks import send_whatsapp_bulk_task
import time

admin_router = APIRouter(tags=["Admin / Operations"])

class ClearWhatsAppFlowSessionRequest(BaseModel):
    phone: str = Field(..., description="Phone number in E.164, e.g. +91XXXXXXXXXX")
    clear_meta_session: bool = Field(
        False,
        description="Also clear Meta flow session key (wa:meta:flow:{phone})",
    )


def _normalize_phone(phone: str) -> str:
    raw = (phone or "").strip()
    if raw.startswith("whatsapp:"):
        raw = raw.replace("whatsapp:", "", 1)
    return raw

@admin_router.get("/admin/stats", summary="Get lead ingestion statistics")
async def get_stats(db: Session = Depends(get_mysql_db)):
    """Provides visibility into lead ingestion health and queue status."""
    try:
        # 1. Total leads today
        today = func.date(Lead.created_at) == func.current_date()
        total_today = db.query(Lead).filter(today).count()

        # 2. CRM status breakdown (today)
        status_counts = db.query(
            Lead.crm_status, func.count(Lead.id)
        ).filter(today).group_by(Lead.crm_status).all()

        # 3. Last sync info
        sync_meta = db.query(SyncMetadata).all()
        sync_info = [
            {
                "source": s.source,
                "last_sync": s.last_sync_at,
                "status": s.status,
                "leads_fetched": s.leads_fetched,
                "last_error": s.last_error
            } for s in sync_meta
        ]

        # 4. Queue backlog
        queue_size = len(lead_queue.job_ids) if lead_queue else 0

        return {
            "today": {
                "total": total_today,
                "breakdown": dict(status_counts)
            },
            "sync_status": sync_info,
            "queue_backlog": queue_size,
        }
    except Exception as e:
        logger.error(f"Failed to fetch admin stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch stats")

@admin_router.get("/admin/analytics", summary="Get simple analytics metrics")
async def analytics(db: Session = Depends(get_mysql_db)):
    """Provides high-level metrics (Total Leads, Today Leads, Failed)."""
    try:
        total_leads = db.query(Lead).count()
        today = func.date(Lead.created_at) == func.current_date()
        today_leads = db.query(Lead).filter(today).count()
        failed = db.query(Lead).filter(Lead.crm_status == "failed").count()

        return {
            "total_leads": total_leads,
            "today_leads": today_leads,
            "failed": failed
        }
    except Exception as e:
        logger.error(f"Failed to fetch analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")


@admin_router.post("/admin/retry-failed", summary="Retry failed CRM syncs")
async def retry_failed_syncs(db: Session = Depends(get_mysql_db)):
    """Replays leads that failed to sync to CRM."""
    if not lead_queue:
        raise HTTPException(status_code=503, detail="Redis Queue not available")

    failed_leads = db.query(Lead).filter(Lead.crm_status == "failed").all()

    requeued_count = 0
    for lead in failed_leads:
        try:
            lead_queue.enqueue(
                sync_lead_to_zoho_task,
                lead.id,
                job_id=f"retry_sync_zoho_{lead.id}"
            )
            lead.crm_status = "queued"
            requeued_count += 1
        except Exception as e:
            logger.error(f"Failed to requeue lead {lead.id}: {e}")

    db.commit()

    return {
        "status": "ok",
        "requeued": requeued_count,
        "total_failed_remaining": db.query(Lead).filter(Lead.crm_status == "failed").count()
    }


@admin_router.post(
    "/admin/whatsapp/bulk",
    summary="Send bulk WhatsApp template messages (queued)",
    response_model=WhatsAppBulkSendResponse,
)
async def send_whatsapp_bulk(
    req: WhatsAppBulkSendRequest,
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_required),
):
    """
    Queues a bulk WhatsApp template send via RQ.
    Requires admin auth.
    """
    if req.dry_run:
        return WhatsAppBulkSendResponse(
            queued=False,
            job_id=None,
            total=len(req.leads),
            dry_run=True,
        )

    if not lead_queue:
        raise HTTPException(status_code=503, detail="Redis Queue not available")

    content_sid = req.content_sid or settings.TWILIO_WHATSAPP_TEMPLATE_SID
    if not content_sid:
        raise HTTPException(status_code=400, detail="content_sid is required (or set TWILIO_WHATSAPP_TEMPLATE_SID)")

    payload = [l.model_dump() for l in req.leads]
    job = lead_queue.enqueue(
        send_whatsapp_bulk_task,
        leads=payload,
        content_sid=content_sid,
        per_message_delay_ms=req.per_message_delay_ms,
        job_id=f"whatsapp_bulk_{int(time.time())}",
    )

    return WhatsAppBulkSendResponse(
        queued=True,
        job_id=job.id,
        total=len(req.leads),
        dry_run=False,
    )


@admin_router.post(
    "/admin/whatsapp/clear-flow-session",
    summary="Clear WhatsApp flow session in Redis (for replay/testing)",
)
async def clear_whatsapp_flow_session(
    req: ClearWhatsAppFlowSessionRequest,
    _admin=Depends(security.admin_required),
):
    """
    Clears Redis conversation state for WhatsApp flow so you can replay from step=interest.
    """
    if not redis_conn:
        raise HTTPException(status_code=503, detail="Redis not available")

    phone = _normalize_phone(req.phone)
    twilio_key = f"wa:flow:{phone}"
    keys_to_clear = [twilio_key]
    if req.clear_meta_session:
        keys_to_clear.append(f"wa:meta:flow:{phone}")

    deleted = {}
    for key in keys_to_clear:
        try:
            # redis `DEL` returns number of keys removed (0 if key doesn't exist)
            deleted[key] = int(redis_conn.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete redis key={key}: {e}")
            deleted[key] = -1

    return {
        "cleared": deleted,
        "phone": phone,
        "status": "ok",
    }
