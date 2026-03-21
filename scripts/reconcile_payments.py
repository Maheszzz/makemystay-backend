#!/usr/bin/env python3
"""
Nightly payment reconciliation job.

Runs every night via cron. For every payment that was created in Razorpay
in the last 24 hours, it checks our local database to ensure it exists and
the statuses match accurately.

If a payment is entirely missing (webhooks failed silently), it is auto-recovered,
a ReconciliationIssue alert is surfaced to the Admin UI, and a LedgerEntry is fired.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

# Allow running from repo root without installing the package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(".env.production")
load_dotenv(".env")

from loguru import logger
import razorpay
from sqlalchemy.orm import Session

from app.configs.db_config import SessionLocal
from app.models.payment import Payment
from app.models.ledger import LedgerEntry
from app.models.reconciliation import ReconciliationIssue

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

def run_reconciliation(hours: int, dry_run: bool):
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
                            status=p_status if p_status in ['success', 'captured', 'failed'] else 'pending',
                            payment_type=p.get('method', 'unknown'),
                            payer_email=p.get('email', ''),
                            payer_phone=p.get('contact', ''),
                            payer_name=None
                        )
                        
                        if p_status in ['captured', 'success']:
                            new_payment.status = "success"
                            
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

        logger.info("=== Reconciliation complete ===")
        logger.info(f"  Total checked    : {len(rzp_payments)}")
        logger.info(f"  Missing & Fixed  : {missing_count}")
        logger.info(f"  Mismatched Status: {mismatch_count}")
        logger.info(f"  Already correct  : {already_correct}")

    except Exception as e:
        logger.error(f"Fatal error in reconciliation script: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile payments vs Razorpay API")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing")
    parser.add_argument("--hours",   type=int, default=24,  help="Look-back window (default 24)")
    args = parser.parse_args()

    started_at = datetime.now(tz=timezone.utc)
    logger.info(
        f"=== Reconciliation started at {started_at.isoformat()} "
        f"(dry_run={args.dry_run}, hours={args.hours}) ==="
    )
    
    run_reconciliation(hours=args.hours, dry_run=args.dry_run)
