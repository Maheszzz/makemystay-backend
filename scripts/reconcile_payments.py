#!/usr/bin/env python3
"""
Nightly payment reconciliation job.

1) Razorpay payment.list (time window): match DB by payment_id; fix missing rows and
   status mismatches.
2) Pending orders in DB: GET /v1/orders/{order_id}/payments (same as admin
   `sync_from_gateway`) to fix rows where webhooks never arrived.

If a payment is entirely missing (webhooks failed silently), it is auto-recovered,
a ReconciliationIssue alert is surfaced to the Admin UI, and a LedgerEntry is fired.
"""

import argparse
import os
import sys
import time
from typing import Optional
from datetime import datetime, timedelta, timezone

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(".env.production")
load_dotenv(".env")

from loguru import logger
import razorpay
from sqlalchemy.orm import Session

from app.api.payment import _fetch_order_payment
from app.configs.db_config import SessionLocal
from app.models.payment import Payment
from app.models.ledger import LedgerEntry
from app.models.reconciliation import ReconciliationIssue
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
if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
    logger.error("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set — aborting.")
    sys.exit(1)

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def _safe_fetch_all_payments_since(since_timestamp: int):
    results = []
    skip = 0
    count = 100
    while True:
        try:
            resp = client.payment.all({
                'from': since_timestamp,
                'count': count,
                'skip': skip
            })
            items = resp.get('items', [])
            if not items:
                break
            results.extend(items)
            
            if len(items) < count:
                break
                
            skip += count
            
            # Rate limiting protection
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Failed to fetch Razorpay paginated: {e}")
            break
            
    return results

def _db_status_from_rzp_payment(p_status: Optional[str]) -> str:
    """Map Razorpay payment.status to our payments.status enum."""
    s = str(p_status or "").lower()
    if s in ("captured", "paid", "success"):
        return "success"
    if s in ("failed",):
        return "failed"
    return "pending"


def run_reconciliation(
    hours: int,
    dry_run: bool,
    *,
    skip_order_backfill: bool = False,
    max_order_backfill: int = 500,
):
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)
        since_ts = int(start_time.timestamp())
        
        logger.info(f"Starting reconciliation job for payments since {start_time.isoformat()}")
        
        # 1. Fetch from Razorpay
        rzp_payments = _safe_fetch_all_payments_since(since_ts)
        logger.info(f"Fetched {len(rzp_payments)} payments from Razorpay API.")
        
        missing_count = 0
        mismatch_count = 0
        already_correct = 0
        
        # 2. Iterate and check our database constraints
        for p in rzp_payments:
            p_id = p.get('id')
            p_status = p.get('status')
            p_amount = p.get('amount', 0)
            
            existing = db.query(Payment).filter(Payment.payment_id == p_id).first()
            
            if not existing:
                missing_count += 1
                logger.warning(f"Reconciliation ALERT: Missing Payment {p_id} ({p_status})")
                
                if not dry_run:
                    try:
                        safe_amount = int(p_amount) / 100
                        safe_order_id = p.get('order_id') or f"reconciled_{p_id}"
                        
                        new_payment = Payment(
                            order_id=safe_order_id,
                            payment_id=p_id,
                            amount=safe_amount,
                            currency=p.get('currency', 'INR'),
                            status=_db_status_from_rzp_payment(p_status),
                            payment_type="booking",
                            payer_email=p.get('email', ''),
                            payer_phone=p.get('contact', ''),
                            payer_name=None
                        )
                        db.add(new_payment)
                        
                        # Apply to Ledger if successfully captured
                        if new_payment.status == "success":
                            ledger_entry = LedgerEntry(
                                payment_id=p_id,
                                entry_type="credit",
                                amount=int(p_amount)
                            )
                            db.add(ledger_entry)
                        
                        # Issue Alert
                        issue = ReconciliationIssue(
                            payment_id=p_id,
                            issue_type="missing_payment",
                            resolved=False
                        )
                        db.add(issue)
                        db.commit()
                        logger.info(f"Auto-recovered missing Payment {p_id} & generated Alert.")
                        
                    except Exception as e:
                        db.rollback()
                        logger.error(f"Failed to auto-recover {p_id}: {e}")
            else:
                db_status = existing.status or ""
                # Mismatch logic
                is_rzp_success = p_status in ['captured', 'success']
                is_db_success = db_status in ['success']
                
                if is_rzp_success and not is_db_success:
                    mismatch_count += 1
                    logger.warning(f"Reconciliation STATUS MISMATCH: {p_id} RZP={p_status} vs DB={db_status}")
                    
                    if not dry_run:
                        existing.status = "success"
                        
                        # Register the newly verified funds into the Ledger
                        ledger_entry = LedgerEntry(
                            payment_id=p_id,
                            entry_type="credit",
                            amount=int(p_amount)
                        )
                        db.add(ledger_entry)
                        
                        issue = ReconciliationIssue(
                            payment_id=p_id,
                            issue_type="status_mismatch",
                            resolved=False
                        )
                        db.add(existing)
                        db.add(issue)
                        db.commit()
                else:
                    already_correct += 1

        # 3) Orders stuck as pending locally (webhooks missed): GET /orders/{id}/payments
        backfilled = 0
        failed_from_order = 0
        if not skip_order_backfill and max_order_backfill > 0:
            pending_local = (
                db.query(Payment)
                .filter(Payment.status == "pending", Payment.order_id.isnot(None))
                .order_by(Payment.created_at.asc())
                .limit(max_order_backfill)
                .all()
            )
            logger.info(
                f"Order/payments backfill: checking {len(pending_local)} pending row(s) "
                f"(max {max_order_backfill})."
            )
            for row in pending_local:
                oid = str(row.order_id)
                try:
                    gp = _fetch_order_payment(oid)
                except Exception as e:
                    logger.warning(f"Backfill fetch failed for {oid}: {e}")
                    gp = None
                time.sleep(0.12)
                if not gp:
                    continue
                ns = _map_status(str(gp.get("status") or ""))
                pid = str(gp.get("id") or "").strip()
                if ns == "success":
                    if not dry_run:
                        row.payment_id = pid or row.payment_id
                        row.status = "success"
                    backfilled += 1
                    logger.info(f"Backfill success: order {oid} -> payment {pid}")
                elif ns == "failed":
                    if not dry_run:
                        row.payment_id = row.payment_id or pid
                        row.status = "failed"
                    failed_from_order += 1
                    logger.info(f"Backfill failed status: order {oid} -> payment {pid}")
            if not dry_run and (backfilled or failed_from_order):
                db.commit()

        logger.info("=== Reconciliation complete ===")
        logger.info(f"  Total checked (RZP list) : {len(rzp_payments)}")
        logger.info(f"  Missing & Fixed          : {missing_count}")
        logger.info(f"  Mismatched Status        : {mismatch_count}")
        logger.info(f"  Already correct          : {already_correct}")
        if not skip_order_backfill:
            logger.info(f"  Order backfill -> success: {backfilled}")
            logger.info(f"  Order backfill -> failed : {failed_from_order}")

    except Exception as e:
        logger.error(f"Fatal error in reconciliation script: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile payments vs Razorpay API")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    parser.add_argument("--hours", type=int, default=24, help="Look-back window for Razorpay payment.list (default 24)")
    parser.add_argument(
        "--skip-order-backfill",
        action="store_true",
        help="Skip GET /orders/{id}/payments for pending DB rows (webhook-miss backfill).",
    )
    parser.add_argument(
        "--max-order-backfill",
        type=int,
        default=500,
        help="Max pending orders to check via order/payments API (default 500).",
    )
    args = parser.parse_args()

    started_at = datetime.now(tz=timezone.utc)
    logger.info(
        f"=== Reconciliation started at {started_at.isoformat()} "
        f"(dry_run={args.dry_run}, hours={args.hours}) ==="
    )
    
    run_reconciliation(
        hours=args.hours,
        dry_run=args.dry_run,
        skip_order_backfill=args.skip_order_backfill,
        max_order_backfill=max(0, args.max_order_backfill),
    )
