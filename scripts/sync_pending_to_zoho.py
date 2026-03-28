"""
Hardened Bulk Zoho CRM sync for leads.

  # Pending only (never successfully linked)
  python scripts/sync_pending_to_zoho.py

  # Re-PUT every lead that already has zoho_lead_id
  python scripts/sync_pending_to_zoho.py --backfill

Features:
- Incremental Batching (50 leads/batch)
- Rate Limit Pausing (10 mins on 429)
- Structured Logging (logs/zoho_sync.log)
- Resumability (skips recently synced in backfill)
"""

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

# from dotenv import load_dotenv  # Handled by app.configs.db_config
from loguru import logger

# load_dotenv()

# Setup Logging
os.makedirs("logs", exist_ok=True)
logger.add("logs/zoho_sync.log", rotation="10 MB", level="INFO")

from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.utils.zoho_adapter import CRMLeadAdapter
from app.utils.zoho_crm_service import ZohoCRMError, ZohoRateLimitError, zoho_crm_service


class SyncStats:
    def __init__(self):
        self.synced = 0
        self.errors = 0
        self.rate_limits = 0

    @property
    def total_processed(self) -> int:
        return self.synced + self.errors

async def sync_batch(db, leads, stats: SyncStats):
    """Syncs a single batch of leads."""
    for lead in leads:
        logger.info(f"Processing Lead #{lead.id} ({lead.phone})...")
        try:
            adapter = CRMLeadAdapter(lead, lead.source)
            zoho_id = await zoho_crm_service.create_or_update_lead(adapter)
            
            lead.zoho_lead_id = zoho_id
            lead.zoho_synced = True
            lead.crm_status = "success"
            lead.updated_at = datetime.now()
            
            db.add(lead)
            db.commit()
            stats.synced += 1
            logger.success(f"Lead #{lead.id} synced: {zoho_id}")
            
        except ZohoRateLimitError as e:
            logger.warning(f"Rate Limit Hit on Lead #{lead.id}: {e}. Pausing for 10 minutes...")
            stats.rate_limits += 1
            db.rollback()
            # Wait 10 minutes
            await asyncio.sleep(600)
            # Re-try this lead once after wait (or just continue to next)
            return "pause"
            
        except (ZohoCRMError, ValueError) as e:
            stats.errors += 1
            logger.error(f"Zoho Error on Lead #{lead.id}: {e}")
            db.rollback()
        except Exception as e:
            stats.errors += 1
            logger.exception(f"Unexpected Error on Lead #{lead.id}: {e}")
            db.rollback()

        await asyncio.sleep(0.5) # Optimized delay
    return "continue"


async def run(*, backfill: bool, limit: Optional[int] = None) -> None:
    logger.info("Starting hardened Zoho CRM bulk sync")
    db = MySQLSessionLocal()
    stats = SyncStats()
    
    batch_size = 25  # Optimized batch size
    offset = 0
    total_to_sync = db.query(Lead).filter(Lead.is_deleted.is_(False)).filter(Lead.zoho_synced.is_(False)).count() if not backfill else db.query(Lead).filter(Lead.is_deleted.is_(False)).filter(Lead.zoho_lead_id.isnot(None)).count()
    logger.info(f"Leads to sync: {total_to_sync}")

    try:
        while True:
            # Construct Query
            query = db.query(Lead).filter(Lead.is_deleted.is_(False))
            
            if backfill:
                query = query.filter(
                    Lead.zoho_lead_id.isnot(None), 
                    Lead.zoho_lead_id != ""
                )
            else:
                query = query.filter(Lead.zoho_synced.is_(False))

            # Apply Limit
            current_limit = batch_size
            if limit is not None and (stats.total_processed + batch_size > limit):
                current_limit = limit - stats.total_processed
            
            if current_limit <= 0:
                break

            leads = query.order_by(Lead.id.asc()).offset(offset).limit(current_limit).all()
            if not leads:
                break

            logger.info(f"Syncing Batch {offset//batch_size + 1} ({len(leads)} leads)...")
            result = await sync_batch(db, leads, stats)
            
            if result == "pause":
                continue
            
            offset += len(leads)
            logger.info(f"Progress: {stats.synced}/{total_to_sync} synced ({stats.errors} errors)")
            
            if limit is not None and (stats.total_processed >= limit):
                break

        logger.info(f"Sync Task Finished. OK={stats.synced} Errors={stats.errors} RateLimits={stats.rate_limits}")
        
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Hardened Zoho CRM Lead Sync")
    p.add_argument("--backfill", action="store_true", help="Sync leads already in Zoho")
    p.add_argument("--limit", type=int, help="Stop after X leads")
    args = p.parse_args()

    asyncio.run(run(backfill=args.backfill, limit=args.limit))


if __name__ == "__main__":
    main()
