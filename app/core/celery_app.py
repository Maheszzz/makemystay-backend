import os
from celery import Celery
from loguru import logger
from app.core.config import settings

redis_url = settings.REDIS_URL

# Initialize the Celery App using Redis as the message broker and result backend
celery_app = Celery(
    "makemystay_worker",
    broker=redis_url,
    backend=redis_url,
    include=[
        "app.api.payment", 
        "app.api.housing", 
        "app.api.realty", 
        "app.api.demo", 
        "app.api.admin",
        "app.tasks.webhook_tasks",
        "app.tasks.lead_tasks",
        "app.tasks.zoho_tasks"
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,       # Max execution time 1 hour
    worker_prefetch_multiplier=1,  # Fair distribution of heavy jobs
    # Run `celery -A app.core.celery_app beat` alongside workers for queue backlog alerts.
    beat_schedule={
        "monitor-celery-queue-backlog": {
            "task": "monitor_celery_queue_backlog",
            "schedule": 300.0,
        },
        "log-zoho-budget-usage": {
            "task": "log_zoho_budget_usage_metric",
            "schedule": 900.0,
        },
        "sync-pending-leads-batch": {
            "task": "sync_pending_leads_batch_task",
            "schedule": 60.0,
        },
    },
    # Ensure Redis doesn't re-queue tasks too early. 1-hour visibility matches task_time_limit.
    broker_transport_options={
        "visibility_timeout": 3600,
    },
)

logger.info(f"Celery App initialized connecting to {redis_url}")
