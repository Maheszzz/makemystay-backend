import os
from celery import Celery
from loguru import logger
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env.production"), override=True)

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

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
        "app.api.admin"
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
