"""
Admin operations: stats, analytics, sync jobs, WhatsApp tools, payment analytics.
"""

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from sqlalchemy import or_
from app.models.realty import Property
from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.redis import HISTORICAL_HOUSING_SYNC_LOCK, lead_queue, redis_conn
from app.models.lead import Lead
from app.schemas.whatsapp import WhatsAppBulkSendRequest, WhatsAppBulkSendResponse
from app.tasks.lead_tasks import sync_lead_to_zoho_task, sync_pending_leads_batch_task
from app.tasks.whatsapp_tasks import send_whatsapp_bulk_task
from app.services.email_service import sync_emails_job

from app.api.admin.schemas import ClearWhatsAppFlowSessionRequest

router = APIRouter()


def _normalize_phone(phone: str) -> str:
    raw = (phone or "").strip()
    if raw.startswith("whatsapp:"):
        raw = raw.replace("whatsapp:", "", 1)
    return raw


@router.post("/retry-failed", summary="Retry failed CRM syncs")
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
    "/sync/zoho-pending-batch",
    summary="Enqueue one Zoho bulk upsert for pending portal leads (99acres/housing batch path)",
)
@limiter.limit("5/minute")
async def trigger_zoho_pending_batch(
    request: Request,
    limit: int = Query(100, ge=1, le=500, description="Max leads per batch (same as Celery task default)"),
    _admin=Depends(security.admin_required),
):
    """Runs `sync_pending_leads_batch_task` once. Portal leads stay `pending` until this job runs;
    normally Celery Beat schedules it every 60s — use this after Beat downtime or to drain backlog."""
    sync_pending_leads_batch_task.delay(limit=limit)
    logger.info("Admin triggered sync_pending_leads_batch_task | limit=%s", limit)
    return {
        "status": "ok",
        "task": "sync_pending_leads_batch_task",
        "limit": limit,
        "hint": "Requires a running Celery worker consuming the default queue.",
    }


@router.post(
    "/sync/email-leads",
    summary="Trigger IMAP email lead sync now",
)
async def trigger_email_lead_sync(
    _admin=Depends(security.admin_required),
):
    """Manually run one email-ingestion cycle for Housing/99acres fallback."""
    summary = await sync_emails_job()
    return {"message": "Email lead sync cycle completed", **summary}


@router.post(
    "/sync/historical-housing",
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

    # Single atomic SET NX — no separate GET (avoids TOCTOU race and double-queue).
    try:
        acquired = redis_conn.set(HISTORICAL_HOUSING_SYNC_LOCK, "1", ex=600, nx=True)
    except Exception as e:
        logger.error(f"Redis lock for historical housing sync: {e}")
        raise HTTPException(status_code=503, detail="Redis unavailable") from e
    if acquired is not True:
        raise HTTPException(status_code=409, detail="A historical sync is already running.")

    from app.tasks.lead_tasks import sync_historical_housing_task

    try:
        task = sync_historical_housing_task.apply_async(kwargs={"days": 5})
    except Exception as e:
        logger.error(f"Failed to queue historical housing Celery task: {e}")
        try:
            redis_conn.delete(HISTORICAL_HOUSING_SYNC_LOCK)
        except Exception:
            pass
        raise HTTPException(status_code=503, detail="Could not queue historical sync task.") from e

    return {"message": "Historical recovery queued successfully via Celery.", "job_id": task.id}


@router.get(
    "/job/{job_id}",
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

    from app.core.celery_app import celery_app
    from celery.result import AsyncResult

    res = AsyncResult(job_id, app=celery_app)
    if res.state != "PENDING" or res.ready():
        status_map = {
            "PENDING": "queued",
            "STARTED": "started",
            "RETRY": "started",
            "SUCCESS": "finished",
            "FAILURE": "failed",
            "REVOKED": "failed",
        }
        return {
            "id": job_id,
            "status": status_map.get(res.state, res.state.lower()),
            "result": str(res.result) if res.ready() else None,
            "error": "Failed" if res.state == "FAILURE" else None,
            "created_at": None,  # Celery doesn't store this by default in the backend without extra config
            "ended_at": None,
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
    except Exception as e:
        logger.error(f"Redis Job fetch failed: {e}")
        raise HTTPException(status_code=503, detail="Error fetching job status from Redis")


@router.get("/search", summary="Global search for Admin")
async def global_search(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_or_employee_required),
):
    search_term = f"%{q}%"
    
    properties = db.query(Property).filter(
        or_(
            Property.property_name.ilike(search_term),
            Property.location.ilike(search_term),
            Property.city.ilike(search_term)
        )
    ).limit(10).all()
    
    leads = db.query(Lead).filter(
        or_(
            Lead.name.ilike(search_term),
            Lead.phone.ilike(search_term),
            Lead.email.ilike(search_term)
        )
    ).limit(10).all()
    
    return {
        "properties": properties,
        "leads": leads
    }


@router.get(
    "/jobs",
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
    "/whatsapp/bulk",
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
    "/whatsapp/clear-flow-session",
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
    "/payments/analytics",
    summary="Get global payment analytics",
)
async def get_payment_analytics(
    month: Optional[str] = Query(None, description="Scope breakdown to calendar month YYYY-MM"),
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_or_employee_required),
):
    from app.services.payment_analytics import payment_analytics_summary
    from app.services.payment_transaction_query import parse_month_range

    if month:
        try:
            parse_month_range(month)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    return payment_analytics_summary(db, month=month)


@router.get(
    "/payments/analytics/series",
    summary="Payment revenue time-series and insights for charts",
)
async def get_payment_analytics_series(
    granularity: str = Query("daily", description="daily | weekly | monthly"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = Query(None, description="Scope to calendar month YYYY-MM"),
    db: Session = Depends(get_mysql_db),
    _user=Depends(security.admin_or_employee_required),
):
    from app.services.payment_analytics import payment_analytics_series
    from app.services.payment_transaction_query import parse_month_range

    if month:
        try:
            parse_month_range(month)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        return payment_analytics_series(
            db,
            granularity=granularity,
            date_from=date_from,
            date_to=date_to,
            month=month,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
