"""
Zoho CRM + ingestion health (DB counts).

Usage:
  PYTHONPATH=. python scripts/check_sync_health.py

Interpreting results:
- **today_leads**: rows where DATE(created_at) = MySQL CURRENT_DATE (server TZ).
- **crm_pending**: 99acres/housing/etc. wait for `sync_pending_leads_batch_task` (Celery Beat every 60s).
- If pending grows: confirm Celery **worker** and **beat** are running, Redis up, and logs for Zoho errors.
"""
import os
import sys
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import func

from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.models.lead_activity import LeadActivity


def check_health():
    db = MySQLSessionLocal()
    try:
        logger.info("Running Zoho CRM Sync Health Check...")

        total = db.query(Lead).filter(Lead.is_deleted.is_(False)).count()
        synced = db.query(Lead).filter(Lead.is_deleted.is_(False), Lead.zoho_synced.is_(True)).count()

        status_rows = db.query(Lead.crm_status, func.count(Lead.id)).group_by(Lead.crm_status).all()
        breakdown = {str(row[0]): int(row[1]) for row in status_rows if row[0] is not None}

        today_filter = func.date(Lead.created_at) == func.current_date()
        today_leads = db.query(Lead).filter(today_filter).count()

        failed = breakdown.get("failed", 0)
        permanently_failed = breakdown.get("permanently_failed", 0)
        pending = breakdown.get("pending", 0)
        processing = breakdown.get("processing", 0)

        print("-" * 44)
        print(f"ZOHO SYNC HEALTH REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 44)
        print(f"Total leads (active):     {total}")
        print(f"Zoho-marked synced:       {synced} ({(synced/total*100) if total else 0:.1f}%)")
        print(f"New rows today (DB date): {today_leads}")
        print("-" * 44)
        print("CRM status breakdown:")
        for k in sorted(breakdown.keys()):
            print(f"  {k:22} {breakdown[k]}")
        print("-" * 44)
        print(f"Pending (batch queue):    {pending}")
        print(f"Processing:               {processing}")
        print(f"Failed (retryable):       {failed}")
        print(f"Permanently failed:       {permanently_failed}")
        print("-" * 44)

        # Recent activity failures (optional context)
        if failed > 0:
            print("\nRecent SYNC_FAILED activity (24h):")
            recent_failures = (
                db.query(LeadActivity)
                .filter(
                    LeadActivity.type == "SYNC_FAILED",
                    LeadActivity.created_at >= datetime.now() - timedelta(days=1),
                )
                .order_by(LeadActivity.created_at.desc())
                .limit(10)
                .all()
            )
            if not recent_failures:
                print("  None in LeadActivity.")
            for act in recent_failures:
                msg = (act.message or "")[:120]
                print(f"  [{act.created_at.strftime('%H:%M')}] Lead #{act.lead_id}: {msg}...")

        if failed > (total * 0.05) and total > 100:
            print("\nWARNING: Failure count above 5% of leads — investigate Zoho API and payloads.")

        if pending > 100:
            print(
                f"\nWARNING: Large pending backlog ({pending}). "
                "Confirm Celery Beat runs `sync_pending_leads_batch_task` every 60s, or POST "
                "/api/v1/admin/sync/zoho-pending-batch once."
            )

        print("-" * 44)
    finally:
        db.close()


if __name__ == "__main__":
    os.environ["PYTHONPATH"] = "."
    check_health()
