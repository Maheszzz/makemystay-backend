"""Daily cap on Zoho CRM HTTP calls (Redis counter). Fail-safe if Redis is unavailable."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from app.core.config import settings
from app.core.redis import redis_conn


class ZohoDailyBudgetExceeded(Exception):
    """Raised when today's Zoho API usage exceeds soft (default 80%) or hard (100%) budget, or Redis fails (fail-safe)."""


def _today_key() -> str:
    # UTC date aligns with Celery enable_utc / server expectations; use NTP in prod for clock sync.
    return f"zoho:api_count:{datetime.now(timezone.utc).date().isoformat()}"


def consume_zoho_api_slot_or_raise() -> None:
    """Increment today's counter; enforce soft then hard limits.

    **Fail-safe:** If Redis is down or ``INCR`` fails, we **block** Zoho calls (do not fail open).
    Set ``ZOHO_DAILY_API_BUDGET=0`` to disable all limits (e.g. local dev without Redis).
    """
    budget = getattr(settings, "ZOHO_DAILY_API_BUDGET", 0) or 0
    if budget <= 0:
        return

    ratio = float(getattr(settings, "ZOHO_DAILY_API_SOFT_LIMIT_RATIO", 0.8) or 0.8)
    soft_threshold = max(1, int(budget * ratio))
    key = _today_key()

    try:
        if not redis_conn:
            logger.error(
                "Redis unavailable — Zoho budget guard fail-safe (blocking Zoho API calls). "
                "Set ZOHO_DAILY_API_BUDGET=0 only for local dev without Redis."
            )
            raise ZohoDailyBudgetExceeded(
                "Redis unavailable; Zoho budget guard cannot run (fail-safe block)"
            )

        n = redis_conn.incr(key)
        if n == 1:
            redis_conn.expire(key, 86400 * 3)

        # Hard cap: absolute ceiling (safety net when soft ratio is 1.0 or misconfigured)
        if n > budget:
            redis_conn.decr(key)
            logger.error(
                f"Zoho daily HARD limit reached | would_be_count={n} | budget={budget}"
            )
            raise ZohoDailyBudgetExceeded(
                f"Zoho API daily HARD limit reached ({budget} calls)"
            )

        # Soft cap: throttle before hard ceiling
        if n > soft_threshold:
            redis_conn.decr(key)
            logger.warning(
                f"Zoho daily soft limit reached | count={n - 1} | threshold={soft_threshold} | budget={budget}"
            )
            raise ZohoDailyBudgetExceeded(
                f"Zoho API daily soft limit ({soft_threshold} calls, {ratio:.0%} of budget {budget}) reached"
            )

    except ZohoDailyBudgetExceeded:
        raise
    except Exception as e:
        logger.error(f"Zoho budget Redis error — fail-safe block: {e}")
        raise ZohoDailyBudgetExceeded(
            f"Zoho budget guard failed (Redis): {e}"
        ) from e


def log_budget_usage_metric() -> None:
    """Periodic log line for dashboards / log aggregators (trends)."""
    budget = getattr(settings, "ZOHO_DAILY_API_BUDGET", 0) or 0
    if budget <= 0:
        return
    n = get_today_zoho_api_count()
    if n is None:
        logger.info("Zoho Budget Usage | used=unknown | remaining=unknown | budget=%s", budget)
        return
    remaining = max(0, budget - n)
    logger.info(
        "Zoho Budget Usage | used=%s | remaining=%s | budget=%s",
        n,
        remaining,
        budget,
    )


def get_today_zoho_api_count() -> Optional[int]:
    """Best-effort count for logs/monitoring; None if Redis unavailable or error."""
    if not redis_conn:
        return None
    try:
        raw = redis_conn.get(_today_key())
        if raw is None:
            return 0
        return int(raw)
    except Exception:
        return None
