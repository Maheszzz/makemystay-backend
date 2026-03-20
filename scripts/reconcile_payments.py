#!/usr/bin/env python3
"""
Nightly payment reconciliation job.

Runs every night via cron. For every payment that is NOT already in a
terminal state (success / failed / expired) it calls the Razorpay API,
compares what Razorpay says with what the DB says, and auto-fixes any
mismatch.

Usage:
    python scripts/reconcile_payments.py [--dry-run] [--hours 24] [--limit 500]

Cron (2 AM daily, server time):
    0 2 * * * cd /home/ubuntu/app && source venv/bin/activate &&
        source .env.production && python scripts/reconcile_payments.py >> logs/reconcile.log 2>&1
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(".env.production")
load_dotenv(".env")

import httpx
from loguru import logger
from sqlalchemy.orm import Session

from app.configs.db_config import SessionLocal
from app.models.payment import Payment
from app.services.payment_normalization import _map_status


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _get_razorpay_creds() -> tuple:
    key_id = os.getenv("RAZORPAY_KEY_ID", "")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not (key_id and key_secret):
        try:
            from app.core.config import settings
            key_id = getattr(settings, "RAZORPAY_KEY_ID", "") or key_id
            key_secret = getattr(settings, "RAZORPAY_KEY_SECRET", "") or key_secret
        except Exception:
            pass
    return key_id, key_secret


RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET = _get_razorpay_creds()
RZ_AUTH             = (RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
RZ_BASE             = "https://api.razorpay.com/v1"

TERMINAL_STATUSES = {"success", "failed", "expired"}


# ---------------------------------------------------------------------------
# Razorpay helpers
# ---------------------------------------------------------------------------

def _fetch_payment(payment_id: str) -> Optional[Dict]:
    """Fetch a single payment entity from Razorpay."""
    try:
        with httpx.Client(timeout=10.0, auth=RZ_AUTH) as http:
            r = http.get(f"{RZ_BASE}/payments/{payment_id}")
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.warning(f"  Razorpay fetch failed for payment_id={payment_id}: {exc}")
        return None


def _fetch_order_payments(order_id: str) -> List[Dict]:
    """Return all payment attempts for a Razorpay order, sorted best-first."""
    try:
        with httpx.Client(timeout=10.0, auth=RZ_AUTH) as http:
            r = http.get(f"{RZ_BASE}/orders/{order_id}/payments")
            r.raise_for_status()
            items = r.json().get("items") or []
            # Prefer captured > authorized > created
            priority = {"captured": 3, "authorized": 2, "created": 1}
            return sorted(
                items,
                key=lambda p: priority.get(str(p.get("status", "")).lower(), 0),
                reverse=True,
            )
    except Exception as exc:
        logger.warning(f"  Razorpay order fetch failed for order_id={order_id}: {exc}")
        return []


# ---------------------------------------------------------------------------
# Reconciliation logic
# ---------------------------------------------------------------------------

def _resolve_gateway_status(row: Payment) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (gateway_status_string, gateway_payment_id) for the given payment row.
    Returns (None, None) if Razorpay is unreachable or the payment doesn't exist there yet.
    """
    if row.payment_id:
        data = _fetch_payment(str(row.payment_id))
        if data:
            return str(data.get("status", "")), str(row.payment_id)

    if row.order_id:
        attempts = _fetch_order_payments(str(row.order_id))
        if attempts:
            best = attempts[0]
            return str(best.get("status", "")), str(best.get("id", "")) or None

    return None, None


def reconcile(db: Session, *, hours: int, dry_run: bool, limit: int) -> dict:
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)

    rows = (
        db.query(Payment)
        .filter(
            Payment.status.notin_(list(TERMINAL_STATUSES)),
            Payment.created_at >= cutoff,
        )
        .order_by(Payment.created_at.desc())
        .limit(limit)
        .all()
    )

    stats = {
        "total_checked": len(rows),
        "fixed_to_success": 0,
        "fixed_to_failed": 0,
        "fixed_payment_id": 0,
        "no_gateway_data": 0,
        "already_correct": 0,
        "errors": 0,
    }

    logger.info(f"Reconciling {len(rows)} non-terminal payments (last {hours}h)…")

    for row in rows:
        try:
            gw_raw, gw_payment_id = _resolve_gateway_status(row)

            if gw_raw is None:
                logger.debug(f"  [{row.order_id}] No gateway data — skipping.")
                stats["no_gateway_data"] += 1
                continue

            gw_status = _map_status(gw_raw)
            db_status = str(row.status)
            changed = False

            if gw_status in TERMINAL_STATUSES and gw_status != db_status:
                logger.info(
                    f"  [{row.order_id}] MISMATCH: DB={db_status} → Gateway={gw_status} (raw={gw_raw})"
                )
                if not dry_run:
                    row.status = gw_status   # type: ignore[assignment]
                changed = True
                if gw_status == "success":
                    stats["fixed_to_success"] += 1
                else:
                    stats["fixed_to_failed"] += 1

            if gw_payment_id and not row.payment_id:
                logger.info(
                    f"  [{row.order_id}] Backfilling payment_id: {gw_payment_id}"
                )
                if not dry_run:
                    row.payment_id = gw_payment_id   # type: ignore[assignment]
                changed = True
                stats["fixed_payment_id"] += 1

            if not changed:
                logger.debug(f"  [{row.order_id}] OK (DB={db_status}, GW={gw_raw})")
                stats["already_correct"] += 1

        except Exception as exc:
            logger.error(f"  [{row.order_id}] Unexpected error: {exc}")
            stats["errors"] += 1

    if not dry_run and db.dirty:
        db.commit()
        logger.info("Changes committed to DB.")
    elif dry_run:
        logger.info("Dry-run — no changes written.")

    return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile payments vs Razorpay API")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    parser.add_argument("--hours",   type=int, default=24,  help="Look-back window (default 24)")
    parser.add_argument("--limit",   type=int, default=500, help="Max rows to check (default 500)")
    args = parser.parse_args()

    if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        logger.error("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — aborting.")
        sys.exit(1)

    started_at = datetime.now(tz=timezone.utc)
    logger.info(
        f"=== Reconciliation started at {started_at.isoformat()} "
        f"(dry_run={args.dry_run}, hours={args.hours}, limit={args.limit}) ==="
    )

    db: Session = SessionLocal()
    try:
        stats = reconcile(db, hours=args.hours, dry_run=args.dry_run, limit=args.limit)
    finally:
        db.close()

    elapsed = (datetime.now(tz=timezone.utc) - started_at).total_seconds()

    logger.info("=== Reconciliation complete ===")
    logger.info(f"  Elapsed          : {elapsed:.1f}s")
    logger.info(f"  Total checked    : {stats['total_checked']}")
    logger.info(f"  Fixed → success  : {stats['fixed_to_success']}")
    logger.info(f"  Fixed → failed   : {stats['fixed_to_failed']}")
    logger.info(f"  Backfilled IDs   : {stats['fixed_payment_id']}")
    logger.info(f"  No gateway data  : {stats['no_gateway_data']}")
    logger.info(f"  Already correct  : {stats['already_correct']}")
    logger.info(f"  Errors           : {stats['errors']}")


if __name__ == "__main__":
    main()
