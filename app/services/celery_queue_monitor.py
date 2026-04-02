"""Celery + Redis queue depth — log when backlog is high; backpressure for new Zoho enqueues."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.redis import redis_conn


def _default_queue_name() -> str:
    return getattr(celery_app.conf, "task_default_queue", None) or "celery"


def get_celery_queue_depth() -> Optional[int]:
    """Length of the default broker queue (``celery`` on Redis), or None if unknown."""
    if not redis_conn:
        return None
    qname = _default_queue_name()
    try:
        return int(redis_conn.llen(qname))
    except Exception:
        return None


def get_backpressure_delay_seconds() -> int:
    """When depth exceeds ``CELERY_QUEUE_BACKLOG_ALERT_THRESHOLD``, add delay to new Zoho sync enqueues."""
    threshold = int(getattr(settings, "CELERY_QUEUE_BACKLOG_ALERT_THRESHOLD", 1000) or 1000)
    extra = int(getattr(settings, "CELERY_BACKPRESSURE_DELAY_SECONDS", 120) or 120)
    if threshold <= 0 or extra <= 0:
        return 0
    d = get_celery_queue_depth()
    if d is None or d <= threshold:
        return 0
    logger.warning(
        f"Celery backpressure | queue_depth={d} | threshold={threshold} | enqueue_delay_s={extra}"
    )
    return extra


def log_celery_queue_backlog_if_high() -> None:
    """If default Celery queue length exceeds threshold, emit an error-level log (alert hook)."""
    threshold = int(getattr(settings, "CELERY_QUEUE_BACKLOG_ALERT_THRESHOLD", 1000) or 1000)
    if threshold <= 0 or not redis_conn:
        return

    qname = _default_queue_name()
    try:
        depth = redis_conn.llen(qname)
    except Exception as e:
        logger.warning(f"Celery queue depth check failed: {e}")
        return

    if depth is None:
        return
    if depth > threshold:
        logger.error(
            f"Celery queue backlog high | queue={qname} | depth={depth} | threshold={threshold} "
            f"| hint=inspect: celery -A app.core.celery_app inspect active"
        )
