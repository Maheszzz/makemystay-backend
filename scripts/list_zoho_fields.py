import asyncio
import os
import httpx
from dotenv import load_dotenv

# Add app directory to sys.path to import settings
import sys
sys.path.append(os.getcwd())

from app.utils.zoho_crm_service import zoho_crm_service

async def list_fields():
    print("Fetching Lead fields from Zoho CRM...")
    result = await zoho_crm_service._make_request("GET", "settings/fields", params={"module": "Leads"})
    if result and "fields" in result:
        for field in result["fields"]:
            if field.get("custom_field"):
                print(f"Custom Field: {field.get('api_name')} ({field.get('field_label')}) - {field.get('data_type')}")
            else:
                print(f"Standard Field: {field.get('api_name')} ({field.get('field_label')}) - {field.get('data_type')}")
    else:
        print(f"Failed to fetch fields: {result}")

async def list_users():
    print("\nFetching Users from Zoho CRM...")
    result = await zoho_crm_service._make_request("GET", "users")
    if result and "users" in result:
        for user in result["users"]:
            print(f"User: {user.get('full_name')} (ID: {user.get('id')}) - {user.get('email')}")
    else:
        print(f"Failed to fetch users: {result}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(list_fields())
    loop.run_until_complete(list_users())
