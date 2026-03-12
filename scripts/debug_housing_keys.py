import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

# Add project root to path
sys.path.append(os.getcwd())

# FORCE load dotenv before EVERYTHING
from dotenv import load_dotenv
load_dotenv()

from app.services.housing_lead_service import housing_lead_service, BUILDER_API_URL

async def run_key_debug():
    print("--- Housing.com Key Discovery ---")
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1) # 1 day range is safe
    
    s_epoch = str(int(start_time.timestamp()))
    e_epoch = str(int(end_time.timestamp()))
    
    leads, err = await housing_lead_service.fetch_leads(s_epoch, e_epoch, api_url=BUILDER_API_URL)
    
    if leads:
        print(f"Keys in a lead object: {leads[0].keys()}")
        import json
        print("\nFull Lead JSON Sample:")
        print(json.dumps(leads[0], indent=2))
    else:
        print("No leads found in this range.")

if __name__ == "__main__":
    asyncio.run(run_key_debug())
