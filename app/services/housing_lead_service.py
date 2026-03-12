"""Housing.com CRM Lead Integration — Pull-based lead fetching.

Fetches leads from Housing.com's Pahal API using HMAC-SHA256 authentication,
deduplicates them, and feeds new leads into the existing lead pipeline.

API Spec: https://pahal.housing.com/api/v0/get-builder-leads (GET)
"""

import hashlib
import hmac
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
from loguru import logger

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
BUILDER_API_URL = "https://pahal.housing.com/api/v0/get-builder-leads"
BROKER_API_URL = "https://pahal.housing.com/api/v0/get-broker-leads"
DEFAULT_PER_PAGE = 1000
REQUEST_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
#  HMAC-SHA256 Hash Generation
# ---------------------------------------------------------------------------
def generate_hmac_hash(api_key: str, timestamp: str) -> str:
    """Generate HMAC-SHA256 hash using the API key and timestamp.

    This mirrors the Ruby snippet from the Housing.com CRM doc:
        Hash(H) = OpenSSL::HMAC.hexdigest(OpenSSL::Digest.new('sha256'), K, T)

    Args:
        api_key: Secret key (K) provided by Housing.com.
        timestamp: Current epoch timestamp as a string (T).

    Returns:
        Hex-encoded HMAC-SHA256 digest.
    """
    return hmac.new(
        api_key.encode("utf-8"),
        timestamp.encode("utf-8"),
        hashlib.sha256,  
    ).hexdigest()


# ---------------------------------------------------------------------------
#  API Client
# ---------------------------------------------------------------------------
class HousingLeadService:
    """Client for Housing.com's Pahal lead-fetching API."""

    def __init__(self):
        self.api_key: str = os.getenv("HOUSING_API_KEY", "")
        self.api_id: str = os.getenv("HOUSING_API_ID", "")
        self.project_ids: str = os.getenv("HOUSING_PROJECT_IDS", "")
        self._last_sync_at: Optional[datetime] = None
        self._last_sync_count: int = 0

    # ------------------------------------------------------------------ #
    #  Public helpers
    # ------------------------------------------------------------------ #

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_id)

    @property
    def last_sync_info(self) -> Dict[str, Any]:
        return {
            "last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at else None,
            "last_sync_count": self._last_sync_count,
            "is_configured": self.is_configured,
        }

    # ------------------------------------------------------------------ #
    #  Fetch leads from Housing.com
    # ------------------------------------------------------------------ #
    async def fetch_leads(
        self,
        start_date: str,
        end_date: str,
        api_url: str = BUILDER_API_URL,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Hit the Housing.com API and return (leads_list, error_message).

        Args:
            start_date: Epoch timestamp string — start of date range.
            end_date:   Epoch timestamp string — end of date range.
            api_url:    Which endpoint to call (builder or broker).
            per_page:   Max records per page (default 1000).

        Returns:
            Tuple of (list_of_lead_dicts, error_string_or_None).
        """
        if not self.is_configured:
            return [], "Housing.com API is not configured (missing HOUSING_API_KEY or HOUSING_API_ID)"

        current_time = str(int(time.time()))
        hash_value = generate_hmac_hash(self.api_key, current_time)

        params: Dict[str, str] = {
            "start_date": start_date,
            "end_date": end_date,
            "current_time": current_time,
            "hash": hash_value,
            "id": self.api_id,
        }

        # Optional project_ids filter
        if self.project_ids:
            params["project_ids"] = self.project_ids

        logger.info(
            f"Housing.com API request: url={api_url}, "
            f"start_date={start_date}, end_date={end_date}, "
            f"current_time={current_time}"
        )

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(api_url, params=params)

            logger.info(f"Housing.com API response: status={response.status_code}")

            if response.status_code == 401:
                return [], "Unauthorized — hash mismatch or request delayed >15 min"

            if response.status_code == 422:
                return [], f"Validation error — missing/invalid params: {response.text}"

            if response.status_code != 200:
                return [], f"Unexpected status {response.status_code}: {response.text}"

            data = response.json()

            # Success response is wrapped in "data" key
            leads = data.get("data", [])
            if not isinstance(leads, list):
                leads = [leads] if leads else []

            logger.info(f"Housing.com API returned {len(leads)} leads")
            return leads, None

        except httpx.TimeoutException:
            return [], "Request timed out"
        except Exception as e:
            logger.error(f"Housing.com API error: {e}")
            return [], str(e)

    # ------------------------------------------------------------------ #
    #  Map Housing.com lead → our LeadCreate fields
    # ------------------------------------------------------------------ #
    @staticmethod
    def map_lead(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a Housing.com lead dict into fields compatible with LeadCreate.

        Actual API response fields (from live testing):
            lead_name, lead_phone, lead_email, flat_id, project_id,
            locality_name, city_name, apartment_names, service_type,
            category_type, min_price, max_price, min_area, max_area,
            country_code, property_field, lead_date (epoch), pg_name
        """
        # Build a contextual message from extra fields
        parts: List[str] = []
        if raw.get("service_type"):
            parts.append(f"Service: {raw['service_type']}")
        if raw.get("category_type"):
            parts.append(f"Category: {raw['category_type']}")
        if raw.get("apartment_names"):
            parts.append(f"Config: {raw['apartment_names']}")
        if raw.get("pg_name"):
            parts.append(f"PG: {raw['pg_name']}")
        if raw.get("locality_name"):
            parts.append(f"Locality: {raw['locality_name']}")
        if raw.get("city_name"):
            parts.append(f"City: {raw['city_name']}")

        project_id = raw.get("project_id") or raw.get("flat_id")
        if project_id:
            parts.append(f"Project/Flat ID: {project_id}")

        # Budget range
        min_price = raw.get("min_price")
        max_price = raw.get("max_price")
        if min_price and max_price:
            parts.append(f"Budget: ₹{min_price} - ₹{max_price}")
        elif min_price:
            parts.append(f"Budget: ₹{min_price}+")

        # Property field (e.g. ["Apartment"])
        prop_field = raw.get("property_field")
        if prop_field and isinstance(prop_field, list):
            parts.append(f"Type: {', '.join(prop_field)}")

        lead_date = raw.get("lead_date")
        if lead_date:
            try:
                dt = datetime.fromtimestamp(int(lead_date))
                parts.append(f"Lead Date: {dt.strftime('%Y-%m-%d %H:%M')}")
            except (ValueError, TypeError, OSError):
                parts.append(f"Lead Date: {lead_date}")

        # Location: prefer locality_name, fall back to city_name
        location = raw.get("locality_name") or raw.get("city_name")

        # Property type: combine service_type + apartment_names
        property_type = raw.get("service_type", "")
        if raw.get("apartment_names"):
            property_type = f"{raw['apartment_names']} ({property_type})"

        # Budget string
        budget = None
        if min_price and max_price:
            budget = f"₹{min_price} - ₹{max_price}"
        elif min_price:
            budget = f"₹{min_price}+"

        return {
            "name": raw.get("lead_name"),
            "phone": raw.get("lead_phone", ""),
            "email": raw.get("lead_email"),
            "project_name": raw.get("project_name"),
            "location": location,
            "property_type": property_type,
            "budget": budget,
            "message": " | ".join(parts) if parts else None,
            "lead_date": lead_date,
            "external_id": str(raw.get("flat_id")) if raw.get("flat_id") else None,
        }

    # ------------------------------------------------------------------ #
    #  Sync: fetch + deduplicate + feed into pipeline
    # ------------------------------------------------------------------ #
    async def sync_leads(
        self,
        start_date: str,
        end_date: str,
        db,
        background_tasks,
        api_url: str = BUILDER_API_URL,
    ) -> Dict[str, Any]:
        """Fetch leads from Housing.com, deduplicate, and process via the pipeline.

        Returns a summary dict with counts and any errors.
        """
        from app.api.webhooks import _process_lead_pipeline
        from app.models.lead import Lead
        from app.schemas.lead import LeadCreate

        leads_raw, error = await self.fetch_leads(start_date, end_date, api_url=api_url)

        if error:
            return {"status": "error", "error": error, "fetched": 0, "imported": 0, "skipped": 0}

        imported = 0
        skipped = 0
        errors: List[str] = []

        for raw_lead in leads_raw:
            mapped = self.map_lead(raw_lead)

            phone = mapped.get("phone", "")
            if not phone or len(phone) < 10:
                skipped += 1
                logger.warning(f"Skipping Housing.com lead with invalid phone: {phone}")
                continue

            # Deduplicate: check if we already have this specific inquiry
            # We check phone + (external_id OR lead_date) for maximum accuracy
            query = db.query(Lead).filter(Lead.phone == phone, Lead.source == "housing")
            
            ext_id = mapped.get("external_id")
            l_date = mapped.get("lead_date")
            
            if ext_id and l_date:
                from sqlalchemy import or_
                query = query.filter(or_(Lead.external_id == ext_id, Lead.lead_date == l_date))
            elif ext_id:
                query = query.filter(Lead.external_id == ext_id)
            elif l_date:
                query = query.filter(Lead.lead_date == l_date)
            
            existing = query.first()
            if existing:
                skipped += 1
                logger.debug(f"Dedup: Housing.com lead phone={phone} date={l_date} already exists (#{existing.id})")
                continue

            # Feed into the shared pipeline
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
                _process_lead_pipeline("housing", payload, background_tasks, db)
                imported += 1
            except Exception as e:
                logger.error(f"Failed to process Housing.com lead (phone={phone}): {e}")
                errors.append(f"phone={phone}: {str(e)}")

        # Track last sync
        self._last_sync_at = datetime.now()
        self._last_sync_count = imported

        result = {
            "status": "ok",
            "fetched": len(leads_raw),
            "imported": imported,
            "skipped": skipped,
        }
        if errors:
            result["errors"] = errors

        logger.info(f"Housing.com sync complete: {result}")
        return result


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------
housing_lead_service = HousingLeadService()
