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
        "app.tasks.lead_tasks"
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
    worker_prefetch_multiplier=1 # Fair distribution of heavy jobs
)

logger.info(f"Celery App initialized connecting to {redis_url}")
