
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core.redis import lead_queue
from app.models.lead import Lead
from app.models.sync_metadata import SyncMetadata
from app.tasks.lead_tasks import sync_lead_to_zoho_task

admin_router = APIRouter(tags=["Admin / Operations"])

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
