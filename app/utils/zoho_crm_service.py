import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


class ZohoCRMService:
    def __init__(self):
        self.client_id = os.getenv("ZOHO_CRM_CLIENT_ID")
        self.client_secret = os.getenv("ZOHO_CRM_CLIENT_SECRET")
        self.refresh_token = os.getenv("ZOHO_CRM_REFRESH_TOKEN")
        self.base_url = "https://www.zohoapis.in/crm/v7"  # Upgraded from v2 to v7
        self.auth_url = "https://accounts.zoho.in/oauth/v2/token"
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    async def _get_access_token(self) -> Optional[str]:
        """Gets or refreshes the access token using the refresh token."""
        if (
            self._access_token
            and self._token_expiry
            and datetime.now() < self._token_expiry
        ):
            return self._access_token

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            logger.error("Zoho CRM credentials missing in environment variables.")
            return None

        params = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(self.auth_url, params=params)
                data = response.json()

                if response.status_code == 200 and "access_token" in data:
                    self._access_token = data["access_token"]
                    expires_in = data.get("expires_in", 3600)
                    self._token_expiry = datetime.now() + timedelta(
                        seconds=expires_in - 60
                    )
                    logger.info("Zoho CRM access token refreshed.")
                    return self._access_token
                else:
                    logger.error(f"Failed to refresh Zoho CRM token: {data}")
                    return None
        except Exception as e:
            logger.error(f"Exception during Zoho CRM token refresh: {str(e)}")
            return None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Utility to make authorized requests to Zoho CRM API."""
        token = await self._get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            async with httpx.AsyncClient() as client:
                if method.upper() == "POST":
                    response = await client.post(
                        url, json=data, headers=headers, params=params
                    )
                elif method.upper() == "PUT":
                    response = await client.put(
                        url, json=data, headers=headers, params=params
                    )
                elif method.upper() in ("GET", "SEARCH"):
                    response = await client.get(url, headers=headers, params=params)
                else:
                    return None

                if response.status_code in [200, 201, 202]:
                    return response.json()
                elif response.status_code == 204:  # No Content
                    return {}
                else:
                    logger.error(
                        f"Zoho CRM API Error ({response.status_code}) [{endpoint}]: {response.text}"
                    )
                    return None
        except Exception as e:
            logger.error(
                f"Exception during Zoho CRM API request [{endpoint}]: {str(e)}"
            )
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
        email = getattr(contact_data, "email", None)
        if not email:
            logger.error("No email found in contact data for Zoho CRM sync.")
            return None

        lead_id = await self.search_lead_by_email(email)

        # Parse name
        first_name = ""
        last_name = "User"  # Zoho requires Last Name

        full_name = getattr(contact_data, "name_", getattr(contact_data, "name", ""))
        if full_name:
            names = full_name.split(" ", 1)
            if len(names) > 1:
                first_name, last_name = names[0], names[1]
            else:
                last_name = names[0]

        # Build description with all extra context
        description_parts = []
        message = getattr(contact_data, "message", "")
        if message:
            description_parts.append(f"Message: {message}")
        location = getattr(contact_data, "location", "")
        if location:
            description_parts.append(f"Location: {location}")
        property_type = getattr(contact_data, "property_type", "")
        if property_type:
            description_parts.append(f"Property Type: {property_type}")
        units = getattr(contact_data, "units", "")
        if units:
            description_parts.append(f"Units: {units}")

        description = " | ".join(description_parts) if description_parts else ""

        payload = {
            "data": [
                {
                    "First_Name": first_name,
                    "Last_Name": last_name,
                    "Email": email,
                    "Phone": getattr(contact_data, "phone", ""),
                    "Company": getattr(contact_data, "company", "Individual"),
                    "Description": description,
                    "Lead_Source": getattr(contact_data, "lead_source", None)
                    or "Website",
                    "City": location,
                }
            ],
            "trigger": ["workflow"],
        }

        if lead_id:
            payload["data"][0]["id"] = lead_id
            result = await self._make_request("PUT", "Leads", data=payload)
            action = "updated"
        else:
            result = await self._make_request("POST", "Leads", data=payload)
            action = "created"

        if result and "data" in result and result["data"][0].get("status") == "success":
            new_id = result["data"][0]["details"]["id"]
            logger.info(f"Zoho CRM Lead {action} successfully: {new_id}")
            return new_id

        logger.error(
            f"Failed to {action} Zoho CRM Lead for {email}. Response: {result}"
        )
        return None

    async def create_demo_event(self, booking_data: Any) -> Optional[str]:
        """Creates a Meeting (Event) in Zoho CRM linked to the Lead via Participants."""
        # 1. Ensure Lead exists
        lead_id = await self.create_or_update_lead(booking_data)
        if not lead_id:
            logger.error("Cannot create event: Lead creation/lookup failed.")
            return None

        # 2. Format times for Zoho CRM (ISO 8601)
        start_time = booking_data.selected_slot
        if start_time.tzinfo is None:
            import pytz

            ist = pytz.timezone("Asia/Kolkata")
            start_time = ist.localize(start_time)

        end_time = start_time + timedelta(minutes=30)

        start_iso = start_time.strftime("%Y-%m-%dT%H:%M:%S%z")
        end_iso = end_time.strftime("%Y-%m-%dT%H:%M:%S%z")
        # Insert colon in timezone offset for ISO 8601 (e.g. +0530 -> +05:30)
        if len(start_iso) >= 5 and start_iso[-5] in ("+", "-"):
            start_iso = start_iso[:-2] + ":" + start_iso[-2:]
        if len(end_iso) >= 5 and end_iso[-5] in ("+", "-"):
            end_iso = end_iso[:-2] + ":" + end_iso[-2:]

        booking_name = getattr(booking_data, "name", "Customer")
        booking_email = getattr(booking_data, "email", "")

        payload = {
            "data": [
                {
                    "Event_Title": f"MakeMyStay Growth Demo - {booking_name}",
                    "Start_DateTime": start_iso,
                    "End_DateTime": end_iso,
                    "Description": f"Demo request for {getattr(booking_data, 'units', 'N/A') or 'N/A'} units.\nMeet Link: {getattr(booking_data, 'meeting_link', 'Pending')}\nLead: {booking_name} ({booking_email})\nPhone: {getattr(booking_data, 'phone', 'N/A')}",
                    "Participants": [
                        {"Email": booking_email, "participant": lead_id, "type": "lead"}
                    ],
                    "Send_Notification": True,
                }
            ]
        }

        result = await self._make_request("POST", "Events", data=payload)

        if result and "data" in result and result["data"][0].get("status") == "success":
            event_id = result["data"][0]["details"]["id"]
            logger.info(f"Zoho CRM Event created successfully: {event_id}")
            return event_id

        logger.error(
            f"Failed to create Zoho CRM Event for {booking_email}. Response: {result}"
        )
        return None

    async def log_call(self, contact_data: Any) -> Optional[str]:
        """Logs a call by appending call info to the Lead's Description in Zoho CRM.

        Uses Leads module (which we have OAuth scope for) instead of
        Notes/Calls modules (which need additional OAuth scopes).
        """
        email = getattr(contact_data, "email", None)
        if not email:
            logger.error("No email found in contact data for Zoho CRM call log.")
            return None

        # Find the lead
        lead_id = await self.search_lead_by_email(email)
        if not lead_id:
            logger.warning(f"No lead found for {email}, skipping call log.")
            return None

        full_name = getattr(
            contact_data, "name_", getattr(contact_data, "name", "Customer")
        )
        phone = getattr(contact_data, "phone", "")
        now = datetime.now().strftime("%Y-%m-%d %H:%M IST")
        message = getattr(contact_data, "message", "N/A")

        # Get existing lead data to preserve description
        lead_data = await self._make_request("GET", f"Leads/{lead_id}")
        existing_desc = ""
        if lead_data and "data" in lead_data:
            existing_desc = lead_data["data"][0].get("Description", "") or ""

        # Append call log to description
        call_log = f"\n\n--- AI Call Log [{now}] ---\nCall to: {phone}\nName: {full_name}\nMessage: {message}\nStatus: Call Initiated via Retell AI"

        new_desc = existing_desc + call_log

        payload = {"data": [{"id": lead_id, "Description": new_desc}]}

        result = await self._make_request("PUT", "Leads", data=payload)

        if result and "data" in result and result["data"][0].get("status") == "success":
            logger.info(f"Zoho CRM call log appended to Lead {lead_id}")
            return lead_id

        logger.error(f"Failed to log call info on Lead for {email}. Response: {result}")
        return None


zoho_crm_service = ZohoCRMService()
