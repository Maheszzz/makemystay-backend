"""Redis-backed Zoho circuit: pause outbound CRM calls when recent failure rate is high."""

from __future__ import annotations

import time
from typing import Optional

from loguru import logger

from app.core.config import settings
from app.core.redis import redis_conn

OPEN_KEY = "zoho:circuit:open_until"
OUTCOMES_KEY = "zoho:circuit:outcomes"
WINDOW_SIZE = 20
MIN_SAMPLES = 10


class ZohoCircuitOpenError(Exception):
    """Outbound Zoho calls temporarily paused (circuit open)."""


def assert_zoho_circuit_allows() -> None:
    """Raise ``ZohoCircuitOpenError`` if circuit is open (no Redis = allow)."""
    if not redis_conn:
        return
    try:
        raw = redis_conn.get(OPEN_KEY)
        if not raw:
            return
        until = float(raw.decode() if isinstance(raw, bytes) else raw)
        if time.time() < until:
            raise ZohoCircuitOpenError(
                f"Zoho circuit open — retry after {int(until - time.time())}s"
            )
    except ZohoCircuitOpenError:
        raise
    except Exception as e:
        logger.warning(f"Zoho circuit check failed (allowing traffic): {e}")


def record_zoho_circuit_success() -> None:
    """Record a successful lead upsert path; clears open circuit."""
    if not redis_conn:
        return
    try:
        redis_conn.lpush(OUTCOMES_KEY, "1")
        redis_conn.ltrim(OUTCOMES_KEY, 0, WINDOW_SIZE - 1)
        redis_conn.delete(OPEN_KEY)
    except Exception as e:
        logger.warning(f"Zoho circuit success record failed: {e}")


def record_zoho_circuit_failure() -> None:
    """Record failure; open circuit if rolling-window failure ratio exceeds threshold."""
    if not redis_conn:
        return
    ratio = float(getattr(settings, "ZOHO_CIRCUIT_FAILURE_RATIO", 0.5) or 0.5)
    pause = int(getattr(settings, "ZOHO_CIRCUIT_PAUSE_SECONDS", 300) or 300)
    try:
        redis_conn.lpush(OUTCOMES_KEY, "0")
        redis_conn.ltrim(OUTCOMES_KEY, 0, WINDOW_SIZE - 1)
        outcomes = redis_conn.lrange(OUTCOMES_KEY, 0, -1)
        if len(outcomes) < MIN_SAMPLES:
            return
        fails = sum(1 for x in outcomes if (x == b"0" or x == "0"))
        n = len(outcomes)
        if n and (fails / n) >= ratio:
            until = time.time() + pause
            redis_conn.set(OPEN_KEY, str(until), ex=pause + 120)
            logger.error(
                f"Zoho circuit OPEN | failure_ratio={fails}/{n}>={ratio:.0%} | pause_s={pause}"
            )
    except Exception as e:
        logger.warning(f"Zoho circuit failure record failed: {e}")


def circuit_open_until_ts() -> Optional[float]:
    """Unix timestamp when circuit closes, or None if closed / unknown."""
    if not redis_conn:
        return None
    try:
        raw = redis_conn.get(OPEN_KEY)
        if not raw:
            return None
        return float(raw.decode() if isinstance(raw, bytes) else raw)
    except Exception:
        return None
