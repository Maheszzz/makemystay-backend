"""Lightweight counters + optional webhook for upload / cleanup events."""

from __future__ import annotations

import json
from typing import Any, Dict

import httpx
from loguru import logger

from app.core.config import settings

_counters: Dict[str, int] = {
    "s3_head_mismatch": 0,
    "s3_head_delete_on_mismatch": 0,
    "s3_head_double_confirm_aborted": 0,
    "s3_orphan_cleanup_deleted_batch": 0,
}


def increment_upload_counter(name: str, amount: int = 1) -> int:
    _counters[name] = _counters.get(name, 0) + amount
    return _counters[name]


def get_upload_counters() -> Dict[str, int]:
    return dict(_counters)


def emit_upload_event(event: str, **extra: Any) -> None:
    """Structured log + optional webhook."""
    payload = {"event": event, **extra}
    logger.info("upload_event {!r}", payload)
    url = settings.ALERT_WEBHOOK_URL
    if not url or not str(url).strip():
        return
    try:
        httpx.post(
            str(url).strip(),
            content=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=5.0,
        )
    except Exception as e:
        logger.warning("ALERT_WEBHOOK_URL post failed: {}", e)
