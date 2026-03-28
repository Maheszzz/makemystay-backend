"""
Daily Zoho CRM Sync Health Report.
Usage: python scripts/check_sync_health.py
"""
import os
import sys
from datetime import datetime, timedelta
from loguru import logger

from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.models.lead_activity import LeadActivity

def check_health():
    db = MySQLSessionLocal()
    try:
        logger.info("Running Zoho CRM Sync Health Check...")
        
        # 1. Overall Stats
        total = db.query(Lead).filter(Lead.is_deleted.is_(False)).count()
        synced = db.query(Lead).filter(Lead.is_deleted.is_(False), Lead.zoho_synced.is_(True)).count()
        failed = db.query(Lead).filter(Lead.crm_status == "failed").count()
        pending = db.query(Lead).filter(Lead.crm_status == "pending", Lead.zoho_synced.is_(False)).count()
        
        print("-" * 40)
        print(f"ZOHO SYNC HEALTH REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("-" * 40)
        print(f"Total Leads:    {total}")
        print(f"Synced:         {synced} ({(synced/total*100) if total else 0:.1f}%)")
        print(f"Failed (DLQ):   {failed}")
        print(f"Pending:        {pending}")
        print("-" * 40)
        
        # 2. Recent Failures
        if failed > 0:
            print("\nRecent Failures (Last 24h):")
            recent_failures = db.query(LeadActivity).filter(
                LeadActivity.type == "SYNC_FAILED",
                LeadActivity.created_at >= datetime.now() - timedelta(days=1)
            ).order_by(LeadActivity.created_at.desc()).limit(10).all()
            
            if not recent_failures:
                print("None recorded in LeadActivity in the last 24h.")
            for act in recent_failures:
                print(f"[{act.created_at.strftime('%H:%M')}] Lead #{act.lead_id}: {act.message[:100]}...")
        
        # 3. Critical Alerts
        if failed > (total * 0.05) and total > 100:
            print("\n⚠️ WARNING: Failure rate is above 5%. Manual intervention highly recommended.")
        
        if pending > 100:
            print("\n⚠️ WARNING: Large backlog of pending leads (count: {pending}). Check if sync script is running.")

        print("-" * 40)
        
    finally:
        db.close()

if __name__ == "__main__":
    os.environ["PYTHONPATH"] = "."
    check_health()
