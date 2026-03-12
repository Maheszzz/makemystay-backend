import os
import sys
import time
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from unittest.mock import MagicMock
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

# FORCE load dotenv before EVERYTHING
from dotenv import load_dotenv
load_dotenv()

from app.services.housing_lead_service import housing_lead_service, BUILDER_API_URL, BROKER_API_URL
from app.configs.db_config import MySQLSessionLocal
from app.models.sync_metadata import SyncMetadata
from app.models.lead import Lead

async def run_full_sync(days_to_fetch=90):
    print("--- Starting Housing.com Debug Sync ---")
    db = MySQLSessionLocal()
    bg = MagicMock()
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_to_fetch)
    
    chunk_delta = timedelta(days=2)
    current_start = start_time

    try:
        while current_start < end_time:
            current_end = min(current_start + chunk_delta, end_time)
            s_epoch = str(int(current_start.timestamp()))
            e_epoch = str(int(current_end.timestamp()))
            
            print(f"Range: {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")
            
            # Use raw fetch to see what's coming back
            leads_builder, err1 = await housing_lead_service.fetch_leads(s_epoch, e_epoch, api_url=BUILDER_API_URL)
            leads_broker, err2 = await housing_lead_service.fetch_leads(s_epoch, e_epoch, api_url=BROKER_API_URL)
            
            if leads_builder:
                print(f"  Builder: {len(leads_builder)} leads found")
                for l in leads_builder[:3]:
                     print(f"    Raw Sample: {l.get('lead_phone')} | {l.get('lead_name')}")
            
            if leads_broker:
                print(f"  Broker: {len(leads_broker)} leads found")
                for l in leads_broker[:3]:
                     print(f"    Raw Sample: {l.get('lead_phone')} | {l.get('lead_name')}")

            current_start += chunk_delta
            await asyncio.sleep(0.5)

    except Exception as e:
        print(f"FATAL ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_full_sync())
