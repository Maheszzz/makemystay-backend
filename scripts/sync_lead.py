import asyncio
import os
import sys
from loguru import logger

# Add app directory to path
sys.path.append(os.getcwd())

from app.configs.db_config import MySQLSessionLocal
from app.repo import lead as lead_repo
from app.utils.zoho_adapter import CRMLeadAdapter
from app.utils.zoho_crm_service import ZohoCRMError, zoho_crm_service

async def sync_specific_lead(lead_id):
    logger.info(f"Syncing Lead #{lead_id} to Zoho...")
    with MySQLSessionLocal() as session:
        lead = lead_repo.get_lead_by_id(session, lead_id)
        if not lead:
            logger.error(f"Lead #{lead_id} not found.")
            return
            
        adapter = CRMLeadAdapter(lead, lead.source)
        payload = adapter.to_zoho_payload()
        logger.info(f"Payload: {payload}")
        
        try:
            result = await zoho_crm_service.create_or_update_lead(adapter)
            logger.success(f"Lead synced successfully. Zoho ID: {result}")
        except (ZohoCRMError, ValueError) as e:
            logger.error(f"Zoho sync failed: {e}")
            raise

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/sync_lead.py <lead_id>")
        sys.exit(1)
    asyncio.run(sync_specific_lead(int(sys.argv[1])))
