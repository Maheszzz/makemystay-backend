import asyncio
import os
import sys
from collections import defaultdict
from loguru import logger

# Add app directory to sys.path to import settings
sys.path.append(os.getcwd())

from app.utils.zoho_crm_service import zoho_crm_service

def normalize_phone(phone: str) -> str:
    """Same normalization used in backend."""
    if not phone:
        return ""
    phone = str(phone).replace(" ", "").replace("-", "")
    if phone.startswith("+91"):
        phone = phone[3:]
    if phone.startswith("0"):
        phone = phone[1:]
    return phone

async def fetch_all_zoho_leads():
    all_leads = []
    page = 1
    per_page = 200
    more_records = True

    logger.info("Fetching leads from Zoho CRM...")
    while more_records:
        params = {"page": page, "per_page": per_page, "fields": "id,Phone,Created_Time,Email"}
        result = await zoho_crm_service._make_request("GET", "Leads", params=params)
        
        if not result or "data" not in result:
            break
            
        data = result["data"]
        all_leads.extend(data)
        
        info = result.get("info", {})
        more_records = info.get("more_records", False)
        logger.info(f"Fetched page {page} ({len(data)} leads). Total so far: {len(all_leads)}")
        page += 1
        
        # Rate limit safety
        await asyncio.sleep(0.5)

    return all_leads

async def delete_zoho_leads(lead_ids):
    if not lead_ids:
        return
        
    logger.info(f"Deleting {len(lead_ids)} leads from Zoho in chunks of 100...")
    # Bulk delete allows up to 100 IDs per request
    batch_size = 100
    for i in range(0, len(lead_ids), batch_size):
        batch = lead_ids[i:i + batch_size]
        ids_str = ",".join(batch)
        params = {"ids": ids_str}
        
        result = await zoho_crm_service._make_request("DELETE", "Leads", params=params)
        logger.info(f"Deleted batch {i//batch_size + 1}/{(len(lead_ids)-1)//batch_size + 1}: {result}")
        await asyncio.sleep(1)

async def main():
    leads = await fetch_all_zoho_leads()
    logger.info(f"Total leads fetched: {len(leads)}")
    
    phone_map = defaultdict(list)
    
    for lead in leads:
        phone = lead.get("Phone")
        if phone:
            norm_phone = normalize_phone(phone)
            phone_map[norm_phone].append(lead)
            
    ids_to_delete = []
    
    for phone, group in phone_map.items():
        if len(group) > 1:
            # Sort by Created_Time to keep the oldest
            # Created_Time format: "2024-03-27T11:52:00+05:30"
            group.sort(key=lambda x: x.get("Created_Time", ""))
            
            # Keep the first one, delete the rest
            kept_lead = group[0]
            duplicates = group[1:]
            
            for d in duplicates:
                ids_to_delete.append(d["id"])
                
    if not ids_to_delete:
        logger.info("No duplicates found in Zoho CRM!")
        return
        
    logger.warning(f"Found {len(ids_to_delete)} duplicate leads to delete from Zoho CRM.")
    
    # Execute deletion
    await delete_zoho_leads(ids_to_delete)
    logger.info("Zoho CRM Duplicate cleanup complete.")

if __name__ == "__main__":
    asyncio.run(main())
