import os
import sys
import time
import asyncio
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_
from unittest.mock import MagicMock
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

# FORCE load dotenv before EVERYTHING
from dotenv import load_dotenv
load_dotenv()

from app.services.housing_lead_service import housing_lead_service, BUILDER_API_URL, BROKER_API_URL
from app.api.webhooks import _process_lead_pipeline
from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.schemas.lead import LeadCreate

async def run_full_sync(days_to_fetch=90):
    print("--- Starting Housing.com REFINED Full Lead Sync ---")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not housing_lead_service.is_configured:
        print("ERROR: Housing API is not configured.")
        return

    db = MySQLSessionLocal()
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days_to_fetch)
    
    total_imported = 0
    total_skipped = 0
    
    chunk_delta = timedelta(days=2)
    current_start = start_time

    try:
        while current_start < end_time:
            current_end = min(current_start + chunk_delta, end_time)
            s_epoch = str(int(current_start.timestamp()))
            e_epoch = str(int(current_end.timestamp()))
            
            print(f"Syncing range: {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}...")
            
            # Fetch both sources
            leads_builder, err1 = await housing_lead_service.fetch_leads(s_epoch, e_epoch, api_url=BUILDER_API_URL)
            leads_broker, err2 = await housing_lead_service.fetch_leads(s_epoch, e_epoch, api_url=BROKER_API_URL)
            
            all_raw = leads_builder + (leads_broker if leads_broker else [])
            
            if not all_raw:
                print("  No leads found.")
            else:
                print(f"  Fetched {len(all_raw)} leads total from both endpoints.")
                
            for raw_lead in all_raw:
                mapped = housing_lead_service.map_lead(raw_lead)
                phone = mapped.get("phone")
                
                if not phone or len(phone) < 10:
                    total_skipped += 1
                    continue
                
                # REFINED DEDUPLICATION
                ext_id = mapped.get("external_id")
                l_date = mapped.get("lead_date")
                
                query = db.query(Lead).filter(Lead.phone == phone, Lead.source == "housing")
                if ext_id and l_date:
                    query = query.filter(or_(Lead.external_id == ext_id, Lead.lead_date == l_date))
                elif ext_id:
                    query = query.filter(Lead.external_id == ext_id)
                elif l_date:
                    query = query.filter(Lead.lead_date == l_date)
                
                existing = query.first()
                if existing:
                    total_skipped += 1
                    continue
                
                # Save to DB and trigger Zoho
                try:
                    payload = LeadCreate(
                        name=mapped.get("name"),
                        phone=phone,
                        email=mapped.get("email"),
                        project_name=mapped.get("project_name"),
                        location=mapped.get("location"),
                        property_type=mapped.get("property_type"),
                        message=mapped.get("message"),
                        lead_date=mapped.get("lead_date"),
                        external_id=mapped.get("external_id"),
                    )
                    
                    # We process inline (simple Mock for background tasks)
                    bg = MagicMock()
                    _process_lead_pipeline("housing", payload, bg, db)
                    total_imported += 1
                except Exception as ex:
                    print(f"  Error processing {phone}: {ex}")

            current_start += chunk_delta
            await asyncio.sleep(0.5)

        print("\n--- Full Sync Complete! ---")
        print(f"Total Imported: {total_imported}")
        print(f"Total Skipped (Duplicates): {total_skipped}")

    except Exception as e:
        print(f"FATAL ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run_full_sync())
