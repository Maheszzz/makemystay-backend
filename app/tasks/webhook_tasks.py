import asyncio
from loguru import logger
from app.core.celery_app import celery_app
from app.configs.db_config import MySQLSessionLocal
from app.schemas.lead import LeadCreate
from app.services.lead_processor import process_lead

@celery_app.task(
    name="process_webhook_lead_task",
    max_retries=3,
    default_retry_delay=5
)
def process_webhook_lead_task(source: str, payload_dict: dict):
    """
    Background worker task to process incoming webhook leads safely
    outside the HTTP request/response cycle.
    """
    logger.info(f"Worker: Processing webhook lead from {source}")
    db = MySQLSessionLocal()
    try:
        lead_data = LeadCreate(**payload_dict)
        # Assuming process_lead is an async function (it is)
        asyncio.run(process_lead(db, lead_data, source, raw_payload=payload_dict))
    except Exception as exc:
        logger.error(f"Worker Error: Failed to process webhook lead from {source}: {exc}")
        # Retry logic
        raise process_webhook_lead_task.retry(exc=exc)
    finally:
        db.close()
