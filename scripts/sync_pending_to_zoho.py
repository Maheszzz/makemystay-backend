import os
import sys
import asyncio
from sqlalchemy.orm import Session
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

# Force load dotenv
from dotenv import load_dotenv
load_dotenv()

from app.configs.db_config import MySQLSessionLocal
from app.models.lead import Lead
from app.repo import lead as lead_repo
from app.schemas.lead import LeadCreate
from app.utils.zoho_crm_service import zoho_crm_service
from app.api.webhooks import _CRMLeadAdapter

async def sync_all_pending():
    print("--- Starting Zoho CRM Bulk Recovery Sync ---")
    db = MySQLSessionLocal()
    
    try:
        # Fetch all leads that haven't been synced to Zoho
        pending_leads = db.query(Lead).filter(Lead.zoho_synced == False).all()
        print(f"Found {len(pending_leads)} pending leads across all sources.")
        
        synced_count = 0
        error_count = 0
        
        for lead in pending_leads:
            print(f"Syncing Lead #{lead.id}: {lead.name} ({lead.phone})...", end="", flush=True)
            
            # Map DB model back to LeadCreate schema for the adapter
            try:
                payload = LeadCreate(
                    name=lead.name,
                    phone=lead.phone,
                    email=lead.email,
                    project_name=lead.project_name,
                    location=lead.location,
                    property_type=lead.property_type,
                    budget=lead.budget,
                    message=lead.message,
                    lead_date=lead.lead_date,
                    external_id=lead.external_id
                )
                
                adapter = _CRMLeadAdapter(payload, lead.source)
                
                zoho_id = await zoho_crm_service.create_or_update_lead(adapter)
                
                if zoho_id:
                    lead.zoho_lead_id = zoho_id
                    lead.zoho_synced = True
                    db.add(lead)
                    db.commit()
                    synced_count += 1
                    print(" SUCCESS")
                else:
                    error_count += 1
                    print(" FAILED (No ID returned)")
                    
            except Exception as e:
                error_count += 1
                print(f" ERROR: {str(e)}")
                db.rollback()
            
            # Small delay to respect Zoho API limits if they exist
            await asyncio.sleep(0.1)
            
        print(f"\n--- Sync Recovery Complete ---")
        print(f"Total Processed: {len(pending_leads)}")
        print(f"Successfully Synced: {synced_count}")
        print(f"Failed: {error_count}")
        
    except Exception as e:
        print(f"FATAL ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(sync_all_pending())
