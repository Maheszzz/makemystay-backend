"""
Bulk Zoho CRM sync for leads.

  # Pending only (never successfully linked)
  python scripts/sync_pending_to_zoho.py

  # Re-PUT every lead that already has zoho_lead_id (backfill empty Lead Status / Substatus / etc.)
  python scripts/sync_pending_to_zoho.py --backfill

Uses CRMLeadAdapter + create_or_update_lead (PUT when zoho_lead_id is set).
"""

import argparse
import asyncio
import os
import sys

sys.path.append(os.getcwd())

from dotenv import load_dotenv

load_dotenv()

from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.utils.zoho_adapter import CRMLeadAdapter
from app.utils.zoho_crm_service import ZohoCRMError, zoho_crm_service


async def run(*, backfill: bool) -> None:
    print("--- Zoho CRM bulk sync ---")
    db = MySQLSessionLocal()

    try:
        if backfill:
            query = (
                db.query(Lead)
                .filter(Lead.zoho_lead_id.isnot(None), Lead.zoho_lead_id != "")
                .filter(Lead.is_deleted.is_(False))
            )
            count = query.count()
            print(f"Backfill mode: {count} leads found. Fetching all...")
            leads = query.all()
            print(f"Fetch complete. Starting sync for {len(leads)} leads.")
        else:
            query = (
                db.query(Lead)
                .filter(Lead.zoho_synced.is_(False))
                .filter(Lead.is_deleted.is_(False))
            )
            count = query.count()
            print(f"Pending mode: {count} leads found. Fetching all...")
            leads = query.all()
            print(f"Fetch complete. Starting sync for {len(leads)} leads.")

        synced_count = 0
        error_count = 0

        for lead in leads:
            print(f"Lead #{lead.id} ({lead.phone})...", end=" ", flush=True)
            try:
                adapter = CRMLeadAdapter(lead, lead.source)
                zoho_id = await zoho_crm_service.create_or_update_lead(adapter)
                lead.zoho_lead_id = zoho_id
                lead.zoho_synced = True
                lead.crm_status = "success"
                db.add(lead)
                db.commit()
                synced_count += 1
                print("OK")
            except (ZohoCRMError, ValueError) as e:
                error_count += 1
                print(f"ZOHO: {e}")
                db.rollback()
            except Exception as e:
                error_count += 1
                print(f"ERROR: {e}")
                db.rollback()

            await asyncio.sleep(0.5)

        print(f"\nDone. OK={synced_count} errors={error_count}")
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Sync leads to Zoho CRM")
    p.add_argument(
        "--backfill",
        action="store_true",
        help="Re-sync all leads that already have zoho_lead_id (forces PUT with full payload).",
    )
    args = p.parse_args()
    asyncio.run(run(backfill=args.backfill))


if __name__ == "__main__":
    main()
