import os
import httpx
from typing import Optional, Dict, Any
from loguru import logger
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

class ZohoCRMService:
    def __init__(self):
        self.client_id = os.getenv("ZOHO_CRM_CLIENT_ID")
        self.client_secret = os.getenv("ZOHO_CRM_CLIENT_SECRET")
        self.refresh_token = os.getenv("ZOHO_CRM_REFRESH_TOKEN")
        self.base_url = "https://www.zohoapis.in/crm/v2"  # Using .in domain based on SMTP config
        self.auth_url = "https://accounts.zoho.in/oauth/v2/token"
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    async def _get_access_token(self) -> Optional[str]:
        """Gets or refreshes the access token using the refresh token."""
        if self._access_token and self._token_expiry and datetime.now() < self._token_expiry:
            return self._access_token

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            logger.error("Zoho CRM credentials missing in environment variables.")
            return None

        params = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token"
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.auth_url, params=params)
                data = response.json()

                if response.status_code == 200 and "access_token" in data:
                    self._access_token = data["access_token"]
                    # Tokens typically last 1 hour (3600 seconds)
                    expires_in = data.get("expires_in", 3600)
                    self._token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)
                    logger.info("Zoho CRM access token refreshed.")
                    return self._access_token
                else:
                    logger.error(f"Failed to refresh Zoho CRM token: {data}")
                    return None
        except Exception as e:
            logger.error(f"Exception during Zoho CRM token refresh: {str(e)}")
            return None

    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Utility to make authorized requests to Zoho CRM API."""
        token = await self._get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json"
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                if method.upper() == "POST":
                    response = await client.post(url, json=data, headers=headers, params=params)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=data, headers=headers, params=params)
                elif method.upper() == "GET":
                    response = await client.get(url, headers=headers, params=params)
                elif method.upper() == "SEARCH":
                    response = await client.get(url, headers=headers, params=params)
                else:
                    return None

                if response.status_code in [200, 201]:
                    return response.json()
                elif response.status_code == 204: # No Content
                    return {}
                else:
                    logger.error(f"Zoho CRM API Error ({response.status_code}): {response.text}")
                    return None
        except Exception as e:
            logger.error(f"Exception during Zoho CRM API request: {str(e)}")
            return None

    async def search_lead_by_email(self, email: str) -> Optional[str]:
        """Searches for a Lead by email and returns the Lead ID if found."""
        params = {"criteria": f"(Email:equals:{email})"}
        result = await self._make_request("GET", "Leads/search", params=params)
        
        if result and "data" in result and len(result["data"]) > 0:
            return result["data"][0]["id"]
        return None

    async def create_or_update_lead(self, contact_data: Any) -> Optional[str]:
        """Creates a new Lead or updates an existing one in Zoho CRM."""
        # Detect if it's ContactCreate or DemoBooking type (duck typing)
        email = getattr(contact_data, 'email', None)
        if not email:
            logger.error("No email found in contact data for Zoho CRM sync.")
            return None

        lead_id = await self.search_lead_by_email(email)
        
        # Map fields
        # Note: name_ is used as alias for name in ContactCreate
        first_name = ""
        last_name = "User" # Zoho requires Last Name
        
        full_name = getattr(contact_data, 'name_', getattr(contact_data, 'name', ''))
        if full_name:
            names = full_name.split(' ', 1)
            if len(names) > 1:
                first_name, last_name = names[0], names[1]
            else:
                last_name = names[0]

        payload = {
            "data": [
                {
                    "First_Name": first_name,
                    "Last_Name": last_name,
                    "Email": email,
                    "Phone": getattr(contact_data, 'phone', ''),
                    "Company": getattr(contact_data, 'company', 'Individual'),
                    "Description": getattr(contact_data, 'message', ''),
                    "Lead_Source": "Website",
                    "City": getattr(contact_data, 'location', ''),
                    "Property_Type": getattr(contact_data, 'property_type', ''), # Custom field? Zoho might need mapping
                    "Units": getattr(contact_data, 'units', '') # Custom field?
                }
            ],
            "trigger": ["workflow"]
        }

        if lead_id:
            # Update existing lead
            payload["data"][0]["id"] = lead_id
            result = await self._make_request("PUT", "Leads", data=payload)
            action = "updated"
        else:
            # Create new lead
            result = await self._make_request("POST", "Leads", data=payload)
            action = "created"

        if result and "data" in result and result["data"][0].get("status") == "success":
            new_id = result["data"][0]["details"]["id"]
            logger.info(f"Zoho CRM Lead {action} successfully: {new_id}")
            return new_id
        
        logger.error(f"Failed to {action} Zoho CRM Lead for {email}")
        return None

    async def create_demo_event(self, booking_data: Any) -> Optional[str]:
        """Creates a Meeting (Event) in Zoho CRM linked to the Lead."""
        # 1. Ensure Lead exists
        lead_id = await self.create_or_update_lead(booking_data)
        if not lead_id:
            return None

        # 2. Format times for Zoho CRM (ISO 8601)
        start_time = booking_data.selected_slot
        if start_time.tzinfo is None:
             import pytz
             start_time = pytz.utc.localize(start_time)
        
        end_time = start_time + timedelta(minutes=30)
        
        # Zoho expects YYYY-MM-DDTHH:mm:ss+HH:mm
        start_iso = start_time.isoformat()
        end_iso = end_time.isoformat()

        payload = {
            "data": [
                {
                    "Event_Title": f"MakeMyStay Growth Demo - {booking_data.name}",
                    "Start_DateTime": start_iso,
                    "End_DateTime": end_iso,
                    "Description": f"Demo request for {booking_data.units or 'N/A'} units. Meet Link: {getattr(booking_data, 'meeting_link', 'Pending')}",
                    "What_Id": { # Link to the Lead
                        "id": lead_id
                    },
                    "$se_module": "Leads",
                    "remind_at": "15 mins",
                    "send_notification": True
                }
            ]
        }

        result = await self._make_request("POST", "Events", data=payload)
        
        if result and "data" in result and result["data"][0].get("status") == "success":
            event_id = result["data"][0]["details"]["id"]
            logger.info(f"Zoho CRM Event created successfully: {event_id}")
            return event_id
        
        logger.error(f"Failed to create Zoho CRM Event for {booking_data.email}")
        return None

zoho_crm_service = ZohoCRMService()
