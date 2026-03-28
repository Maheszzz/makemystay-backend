import asyncio
import os
import sys
from loguru import logger

# Add app directory to path
sys.path.append(os.getcwd())

from app.utils.zoho_crm_service import zoho_crm_service

async def fetch_zoho_fields():
    logger.info("Fetching Zoho CRM Leads module fields...")
    result = await zoho_crm_service._make_request("GET", "settings/fields?module=Leads")
    
    if result and "fields" in result:
        logger.success(f"Found {len(result['fields'])} fields.")
        # Look for status related fields
        for field in result["fields"]:
            api_name = field.get("api_name")
            display_label = field.get("display_label")
            if "status" in api_name.lower() or "status" in display_label.lower() or "inquiry" in api_name.lower():
                logger.info(f"Field: {display_label} | API Name: {api_name} | Type: {field.get('data_type')}")
    else:
        logger.error(f"Failed to fetch fields: {result}")

if __name__ == "__main__":
    asyncio.run(fetch_zoho_fields())
