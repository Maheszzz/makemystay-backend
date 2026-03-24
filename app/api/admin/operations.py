"""
Admin operations: stats, analytics, sync jobs, WhatsApp tools, payment analytics.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.redis import lead_queue, redis_conn
from app.models.lead import Lead
from app.schemas.whatsapp import WhatsAppBulkSendRequest, WhatsAppBulkSendResponse
from app.tasks.lead_tasks import sync_lead_to_zoho_task
from app.tasks.whatsapp_tasks import send_whatsapp_bulk_task
from app.services.email_service import sync_emails_job

from app.api.admin.schemas import ClearWhatsAppFlowSessionRequest

router = APIRouter()


def _normalize_phone(phone: str) -> str:
    raw = (phone or "").strip()
    if raw.startswith("whatsapp:"):
        raw = raw.replace("whatsapp:", "", 1)
    return raw


@router.post("/admin/retry-failed", summary="Retry failed CRM syncs")
async def retry_failed_syncs(
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_or_employee_required),
):
    """Requeues leads with crm_status=failed for Zoho sync (admin or employee JWT)."""
    if not lead_queue:
        raise HTTPException(status_code=503, detail="Redis Queue not available")

    failed_leads = db.query(Lead).filter(Lead.crm_status == "failed").all()

    requeued_count = 0
    for lead in failed_leads:
        try:
            lead_queue.enqueue(sync_lead_to_zoho_task, lead.id, job_id=f"retry_sync_zoho_{lead.id}")
            lead.crm_status = "queued"
            requeued_count += 1
        except Exception as e:
            logger.error(f"Failed to requeue lead {lead.id}: {e}")

    db.commit()

    return {
        "status": "ok",
        "requeued": requeued_count,
        "total_failed_remaining": db.query(Lead).filter(Lead.crm_status == "failed").count(),
    }


@router.post(
    "/admin/sync/email-leads",
    summary="Trigger IMAP email lead sync now",
)
async def trigger_email_lead_sync(
    _admin=Depends(security.admin_required),
):
    """Manually run one email-ingestion cycle for Housing/99acres fallback."""
    summary = await sync_emails_job()
    return {"message": "Email lead sync cycle completed", **summary}


@router.post(
    "/admin/sync/historical-housing",
    summary="Trigger historical Housing.com lead recovery (last 5 days)",
)
@limiter.limit("2/minute")
async def trigger_historical_housing_sync(
    request: Request,
    _admin=Depends(security.admin_required),
):
    """Manually enqueue an RQ job to fetch the last 5 days of missing leads."""
    if not lead_queue or not redis_conn:
        raise HTTPException(status_code=503, detail="Redis queue not available")

    lock_key = "lock:historical_sync_housing"
    if redis_conn.get(lock_key):
        raise HTTPException(status_code=409, detail="A historical sync is already running.")
    redis_conn.set(lock_key, "1", ex=600, nx=True)

    from app.tasks.lead_tasks import sync_historical_housing_task

    # Queue via Celery instead of legacy RQ to prevent pickling errors
    task = sync_historical_housing_task.apply_async(kwargs={"days": 5})

    return {"message": "Historical recovery queued successfully via Celery.", "job_id": task.id}


@router.get(
    "/admin/job/{job_id}",
    summary="Get status of a background RQ or Celery job",
)
async def get_job_status(job_id: str, db: Session = Depends(get_mysql_db), _admin=Depends(security.admin_required)):
    """Fetch realtime progress and result of a background job."""
    from app.models.sync_job import SyncJob

    celery_job = db.query(SyncJob).filter(SyncJob.task_id == job_id).first()
    if celery_job:
        status_map = {
            "pending": "queued",
            "running": "started",
            "success": "finished",
            "failed": "failed",
        }
        return {
            "id": celery_job.task_id,
            "status": status_map.get(celery_job.status, celery_job.status),
            "result": celery_job.result,
            "error": celery_job.error,
            "created_at": celery_job.created_at.isoformat() if celery_job.created_at else None,
            "ended_at": celery_job.completed_at.isoformat() if celery_job.completed_at else None,
        }

    if not redis_conn:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    from rq.job import Job
    from rq.exceptions import NoSuchJobError

    try:
        job = Job.fetch(job_id, connection=redis_conn)
        status = job.get_status()
        return {
            "id": job.id,
            "status": status,
            "result": job.result,
            "error": "Failed" if job.exc_info else None,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }
    except NoSuchJobError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get(
    "/admin/jobs",
    summary="Get history of all Celery Sync Jobs",
)
async def get_all_jobs(db: Session = Depends(get_mysql_db), _admin=Depends(security.admin_required)):
    from app.models.sync_job import SyncJob

    jobs = db.query(SyncJob).order_by(SyncJob.created_at.desc()).limit(50).all()
    return [
        {
            "id": j.task_id,
            "task_name": j.task_name,
            "status": j.status,
            "result": j.result,
            "error": j.error,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
        for j in jobs
    ]


@router.post(
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


@router.post(
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
            deleted[key] = int(redis_conn.delete(key))
        except Exception as e:
            logger.error(f"Failed to delete redis key={key}: {e}")
            deleted[key] = -1

    return {
        "cleared": deleted,
        "phone": phone,
        "status": "ok",
    }


@router.get(
    "/admin/payments/analytics",
    summary="Get global payment analytics",
)
async def get_payment_analytics(
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_or_employee_required),
):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func
    from app.models.payment import Payment
    from app.models.payment_webhook_event import PaymentWebhookEvent
    from app.models.reconciliation import ReconciliationIssue

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    success_all = db.query(func.sum(Payment.amount)).filter(Payment.status == "success").scalar() or 0
    success_today = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == "success", Payment.created_at >= today_start)
        .scalar()
        or 0
    )
    success_month = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == "success", Payment.created_at >= month_start)
        .scalar()
        or 0
    )

    counts = db.query(Payment.status, func.count(Payment.id)).group_by(Payment.status).all()
    count_dict = {str(status).lower(): count for status, count in counts}

    refunded_count = count_dict.get("refunded", 0)

    alert_window_start = now - timedelta(days=14)
    risky_ignored_reasons = {
        "identifiers_missing",
        "payment_creation_failed",
        "event_not_mapped",
    }
    ignored_webhooks = (
        db.query(func.count(PaymentWebhookEvent.id))
        .filter(
            PaymentWebhookEvent.status == "ignored",
            PaymentWebhookEvent.reason.in_(risky_ignored_reasons),
            PaymentWebhookEvent.created_at >= alert_window_start,
        )
        .scalar()
        or 0
    )
    # Only `error` = operational failure (e.g. secret not configured, DB log failure).
    # `rejected` = missing/invalid signature or bad JSON — normal internet noise; do not alert.
    failed_webhooks = (
        db.query(func.count(PaymentWebhookEvent.id))
        .filter(
            PaymentWebhookEvent.status == "error",
            PaymentWebhookEvent.created_at >= alert_window_start,
        )
        .scalar()
        or 0
    )
    rejected_inbound_webhooks = (
        db.query(func.count(PaymentWebhookEvent.id))
        .filter(
            PaymentWebhookEvent.status == "rejected",
            PaymentWebhookEvent.created_at >= alert_window_start,
        )
        .scalar()
        or 0
    )
    reconciliation_mismatches = (
        db.query(func.count(ReconciliationIssue.id)).filter(ReconciliationIssue.resolved == False).scalar() or 0
    )

    return {
        "revenue_total_all_time": float(success_all),
        "revenue_today": float(success_today),
        "revenue_this_month": float(success_month),
        "payments_breakdown": {
            "success": count_dict.get("success", 0),
            "pending": count_dict.get("pending", 0),
            "failed": count_dict.get("failed", 0),
            "refunded": refunded_count,
            "expired": count_dict.get("expired", 0),
        },
        "alerts": {
            "ignored_webhooks": ignored_webhooks,
            "failed_webhooks": failed_webhooks,
            "rejected_inbound_webhooks": rejected_inbound_webhooks,
            "reconciliation_mismatches": reconciliation_mismatches,
        },
    }
