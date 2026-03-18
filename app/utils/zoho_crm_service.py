from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import httpx
import pybreaker
from dotenv import load_dotenv
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

# Circuit breaker for Zoho CRM: trips after 5 failures, resets after 60s
zoho_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)

load_dotenv()

# ------------------------------------------------------------------ #
#  Human-friendly source names for Zoho CRM Lead_Source
# ------------------------------------------------------------------ #
SOURCE_DISPLAY_NAMES = {
    "housing": "Housing.com",
    "99acres": "99acres",
    "magicbricks": "MagicBricks",
    "meta": "Meta Ads",
    "website": "Website",
    "broker": "Broker Referral",
}

from app.core.redis import redis_conn
from app.utils.zoho_adapter import CRMLeadAdapter


class ZohoCRMService:
    def __init__(self):
        self.client_id = settings.ZOHO_CRM_CLIENT_ID
        self.client_secret = settings.ZOHO_CRM_CLIENT_SECRET
        self.refresh_token = settings.ZOHO_CRM_REFRESH_TOKEN
        self.base_url = "https://www.zohoapis.in/crm/v7"  # Upgraded from v2 to v7
        self.auth_url = "https://accounts.zoho.in/oauth/v2/token"
        self._access_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True
    )
    async def _get_access_token(self) -> Optional[str]:
        """Gets or refreshes the access token using the refresh token. Uses Redis for caching."""
        # 1. Check in-memory cache
        if (
            self._access_token
            and self._token_expiry
            and datetime.now() < self._token_expiry
        ):
            return self._access_token

        # 2. Check Redis cache
        if redis_conn:
            cached_token = redis_conn.get("zoho_access_token")
            if cached_token:
                self._access_token = cached_token.decode("utf-8")
                ttl = redis_conn.ttl("zoho_access_token")
                self._token_expiry = datetime.now() + timedelta(seconds=ttl)
                logger.info("Zoho CRM access token retrieved from Redis.")
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
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self.auth_url, params=params)
                data = response.json()

                if response.status_code == 200 and "access_token" in data:
                    token = data["access_token"]
                    expires_in = data.get("expires_in", 3600)

                    self._access_token = token
                    self._token_expiry = datetime.now() + timedelta(
                        seconds=expires_in - 60
                    )

                    # 3. Cache in Redis
                    if redis_conn:
                        redis_conn.set("zoho_access_token", token, ex=expires_in - 60)

                    logger.info("Zoho CRM access token refreshed and cached.")
                    return token
                else:
                    logger.error(f"Failed to refresh Zoho CRM token: {data}")
                    return None
        except Exception as e:
            logger.error(f"Exception during Zoho CRM token refresh: {str(e)}")
            return None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True
    )
    @zoho_breaker
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Utility to make authorized university requests to Zoho CRM API."""
        token = await self._get_access_token()
        if not token:
            return None

        headers = {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/{endpoint}"

        try:
            # Use shorter timeout for fail-fast
            async with httpx.AsyncClient(timeout=10.0) as client:
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
                elif response.status_code == 429: # Rate limit
                    logger.error(f"Zoho CRM Rate Limit Exceeded: {response.text}")
                    raise httpx.RequestError("Zoho CRM Rate Limit Exceeded")
                else:
                    logger.error(
                        f"Zoho CRM API Error ({response.status_code}) [{endpoint}]: {response.text}"
                    )
                    return None
        except Exception as e:
            logger.error(
                f"Exception during Zoho CRM API request [{endpoint}]: {str(e)}"
            )
            # Re-raise for retry decorator if it's a timeout/error
            if isinstance(e, (httpx.TimeoutException, httpx.RequestError)):
                raise e
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
        # Use adapter for mapping if it's not already a dict
        if isinstance(contact_data, CRMLeadAdapter):
            payload_data = contact_data.to_zoho_payload()
        elif hasattr(contact_data, "to_zoho_payload"):
            payload_data = contact_data.to_zoho_payload()
        else:
            # Fallback for generic objects (like DemoBooking)
            # Ideally we should use the adapter everywhere
            adapter = CRMLeadAdapter(contact_data, getattr(contact_data, "lead_source", "Website"))
            payload_data = adapter.to_zoho_payload()

        email = payload_data.get("Email")
        if not email:
            logger.error("No email found in contact data for Zoho CRM sync.")
            return None

        lead_id = await self.search_lead_by_email(email)

        payload = {
            "data": [payload_data],
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
