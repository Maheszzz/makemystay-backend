"""Housing.com CRM Lead Integration — Pull-based lead fetching.

Fetches leads from Housing.com's Pahal API using HMAC-SHA256 authentication,
deduplicates them, and feeds new leads into the existing lead pipeline.

API Spec: https://pahal.housing.com/api/v0/get-builder-leads (GET)
"""

import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pybreaker
from aiolimiter import AsyncLimiter
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

# ---------------------------------------------------------------------------
#  Constants
# ---------------------------------------------------------------------------
BUILDER_API_URL = "https://pahal.housing.com/api/v0/get-builder-leads"
BROKER_API_URL = "https://pahal.housing.com/api/v0/get-broker-leads"
DEFAULT_PER_PAGE = 1000
BOOTSTRAP_FETCH_DAYS = 2  # fetch last 2 days on first run
REQUEST_TIMEOUT = 15.0    # seconds — Housing.com bulk endpoint can be slow

# --- Scale-Proof Controls ---
_limiters = {}
_semaphores = {}


def extract_housing_leads(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize Housing API responses across schema variants.

    Housing has returned leads as `leads` historically and `data` in newer
    responses. We accept both to avoid silent lead drops.
    """
    if not isinstance(payload, dict):
        return []

    for key in ("leads", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    # Defensive fallback for nested wrappers.
    nested = payload.get("result")
    if isinstance(nested, dict):
        for key in ("leads", "data"):
            value = nested.get(key)
            if isinstance(value, list):
                return value

    return []

def get_housing_limiter() -> AsyncLimiter:
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = AsyncLimiter(10, 1)
    return _limiters[loop]

def get_housing_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(5)
    return _semaphores[loop]

# Circuit breaker: trips after 5 failures, resets after 60s
housing_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)


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
        self.api_key: str = settings.HOUSING_API_KEY
        self.api_id: str = settings.HOUSING_API_ID
        self.project_ids: str = "" # Add this to settings later if needed
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
            "last_sync_at": (self._last_sync_at or datetime.now()).isoformat() if self._last_sync_at else None,
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
        """Hit the Housing.com API and return (leads_list, error_message) with chunking.

        Housing com API breaks if the diff between start_date and end_date > 48hrs. 
        So we chunk by 48 hours.
        """
        return await self._fetch_leads_with_retry(start_date, end_date, api_url, per_page)

    async def _fetch_leads_with_retry(
        self,
        start_date: str,
        end_date: str,
        api_url: str = BUILDER_API_URL,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Split the date window into ≤48 h chunks and fetch them concurrently.

        Retry is applied at the *chunk* level (see _safe_fetch_single_chunk) so
        one chunk failure retries only that chunk, not the entire batch.
        """
        if not self.is_configured:
            return [], "Housing.com API not configured (HOUSING_API_KEY / HOUSING_API_ID missing)"

        s_dt = datetime.fromtimestamp(int(start_date))
        e_dt = datetime.fromtimestamp(int(end_date))

        tasks = []
        current_start = s_dt
        while current_start < e_dt:
            current_end = min(current_start + timedelta(hours=48), e_dt)
            tasks.append(
                self._safe_fetch_single_chunk(
                    api_url,
                    str(int(current_start.timestamp())),
                    str(int(current_end.timestamp())),
                    per_page,
                )
            )
            current_start = current_end

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        all_leads: List[Dict[str, Any]] = []
        for resp in responses:
            if isinstance(resp, Exception):
                logger.error(f"Housing chunk raised: {resp}")
                continue
            if not isinstance(resp, tuple):
                logger.error(f"Housing chunk returned unexpected type: {resp!r}")
                continue
            chunk_leads, error = resp
            if error:
                logger.error(f"Housing chunk error: {error}")
                continue
            all_leads.extend(chunk_leads)

        return all_leads, None

    async def _safe_fetch_single_chunk(self, *args, **kwargs):
        """Wrapper to apply concurrency and rate limiting."""
        async with get_housing_semaphore():
            async with get_housing_limiter():
                return await self._fetch_single_chunk_protected(*args, **kwargs)

    @housing_breaker
    async def _fetch_single_chunk_protected(
        self,
        api_url: str,
        start_date: str,
        end_date: str,
        per_page: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Protected fetch call wrapped by circuit breaker."""
        # This is the actual network call
        return await self._fetch_single_chunk_raw(api_url, start_date, end_date, per_page)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _fetch_single_chunk_raw(
        self,
        api_url: str,
        start_date: str,
        end_date: str,
        per_page: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """The actual raw network call to Housing.com."""
        current_time = str(int(time.time()))
        hash_value = generate_hmac_hash(self.api_key, current_time)

        params: Dict[str, str] = {
            "start_date": start_date,
            "end_date": end_date,
            "current_time": current_time,
            "hash": hash_value,
            "id": self.api_id,
        }

        if self.project_ids:
            params["project_ids"] = self.project_ids

        logger.info(
            f"Housing.com API chunk request: url={api_url}, "
            f"start_date={start_date}, end_date={end_date}"
        )

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.get(api_url, params=params)

                if response.status_code == 200:
                    data = response.json()
                    leads = extract_housing_leads(data)
                    if "leads" not in data and "data" in data:
                        logger.warning(
                            "Housing API response used 'data' key instead of 'leads'; "
                            f"parsed {len(leads)} records"
                        )
                    return leads, None
                else:
                    logger.error(f"Housing.com API Error {response.status_code}: {response.text}")
                    return [], f"API Error ({response.status_code})"
        except Exception as e:
            logger.error(f"Housing.com API Exception: {e}")
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

        # external_id: prefer flat_id (most specific), fall back to project_id
        flat_id    = raw.get("flat_id")
        project_id_val = raw.get("project_id")
        external_id = (
            str(flat_id) if flat_id
            else str(project_id_val) if project_id_val
            else None
        )

        return {
            "name":          raw.get("lead_name"),
            "phone":         raw.get("lead_phone", ""),
            "email":         raw.get("lead_email"),
            "project_name":  raw.get("project_name"),
            "location":      location,
            "property_type": property_type,
            "budget":        budget,
            "message":       " | ".join(parts) if parts else None,
            "lead_date":     lead_date,
            "external_id":   external_id,
        }

    # ------------------------------------------------------------------ #
    #  Sync: fetch + deduplicate + feed into pipeline
    # ------------------------------------------------------------------ #
    async def sync_leads(
        self,
        start_date: str,
        end_date: str,
        db,
        background_tasks=None,
        api_url: str = BUILDER_API_URL,
    ) -> Dict[str, Any]:
        """Fetch leads from Housing.com, deduplicate, and process via the pipeline.

        Args:
            background_tasks: Deprecated, kept for backward compatibility.

        Returns a summary dict with counts and any errors.
        """
        from app.models.lead import Lead
        from app.schemas.lead import LeadCreate
        from app.services.lead_processor import process_lead

        leads_raw, error = await self.fetch_leads(start_date, end_date, api_url=api_url)

        if error:
            return {"status": "error", "error": error, "fetched": 0, "imported": 0, "skipped": 0}

        imported: int = 0
        skipped: int = 0
        errors: List[str] = []

        for raw_lead in leads_raw:
            mapped = self.map_lead(raw_lead)

            phone = mapped.get("phone", "")
            if not phone or len(phone) < 10:
                skipped += 1  # type: ignore[operator]
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
                skipped += 1  # type: ignore[operator]
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
                await process_lead(db, payload, "housing", raw_payload=raw_lead)
                imported += 1  # type: ignore[operator]
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
