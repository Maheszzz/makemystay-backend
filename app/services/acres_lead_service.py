"""99acres CRM Lead Integration — Pull-based lead fetching.

Fetches leads from 99acres' private Fetch Leads API using an API key,
deduplicates them, and feeds new leads into the existing lead pipeline.

API Spec: https://www.99acres.com/api/fetch-leads (GET)
Params:   api_key, from_date (epoch), to_date (epoch), page, per_page
Response: JSON { leads: [...], total: N }

Each lead record contains:
    query_id, name, mobile (also: phone), email, city, locality,
    property_type, budget, project_name, created_at (epoch), message
"""

import asyncio
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
DEFAULT_PER_PAGE = 500
REQUEST_TIMEOUT = 20.0  # seconds

# --- Per-event-loop concurrency controls ---
_limiters: Dict[Any, AsyncLimiter] = {}
_semaphores: Dict[Any, asyncio.Semaphore] = {}


def _get_limiter() -> AsyncLimiter:
    loop = asyncio.get_running_loop()
    if loop not in _limiters:
        _limiters[loop] = AsyncLimiter(5, 1)  # 5 req/s
    return _limiters[loop]


def _get_semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    if loop not in _semaphores:
        _semaphores[loop] = asyncio.Semaphore(3)
    return _semaphores[loop]


# Circuit breaker: trips after 5 failures, resets after 60 s
acres_breaker = pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60)


# ---------------------------------------------------------------------------
#  Response normaliser
# ---------------------------------------------------------------------------
def extract_99acres_leads(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise 99acres API responses across possible schema variants.

    99acres may return leads under `leads`, `data`, or nested `result.leads`.
    Accept all variants to avoid silent lead drops.
    """
    if not isinstance(payload, dict):
        return []

    for key in ("leads", "data", "queries", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    # Nested variant
    nested = payload.get("result") or payload.get("response")
    if isinstance(nested, dict):
        for key in ("leads", "data", "queries"):
            value = nested.get(key)
            if isinstance(value, list):
                return value

    return []


# ---------------------------------------------------------------------------
#  API Client
# ---------------------------------------------------------------------------
class AcresLeadService:
    """Client for 99acres' private Fetch Leads API."""

    def __init__(self) -> None:
        self.api_key: str = getattr(settings, "ACRES_API_KEY", "")
        self.api_url: str = getattr(
            settings,
            "ACRES_API_URL",
            "https://www.99acres.com/api/fetch-leads",
        )
        self._last_sync_at: Optional[datetime] = None
        self._last_sync_count: int = 0

    # ------------------------------------------------------------------ #
    #  Public helpers
    # ------------------------------------------------------------------ #

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def last_sync_info(self) -> Dict[str, Any]:
        return {
            "last_sync_at": self._last_sync_at.isoformat() if self._last_sync_at else None,
            "last_sync_count": self._last_sync_count,
            "is_configured": self.is_configured,
        }

    # ------------------------------------------------------------------ #
    #  Fetch leads (public entry point)
    # ------------------------------------------------------------------ #
    async def fetch_leads(
        self,
        from_date: str,
        to_date: str,
        per_page: int = DEFAULT_PER_PAGE,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetch leads from 99acres for the given epoch window.

        Chunks the window into ≤ 48-hour slices and fetches concurrently to
        stay within any server-side date range limits.

        Returns:
            (leads_list, error_message)  — error_message is None on success.
        """
        if not self.is_configured:
            return [], "99acres pull API not configured — ACRES_API_KEY is missing"

        s_dt = datetime.fromtimestamp(int(from_date))
        e_dt = datetime.fromtimestamp(int(to_date))

        tasks = []
        current_start = s_dt
        while current_start < e_dt:
            current_end = min(current_start + timedelta(hours=48), e_dt)
            tasks.append(
                self._safe_fetch_chunk(
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
                logger.error(f"99acres chunk raised: {resp}")
                continue
            if not isinstance(resp, tuple):
                logger.error(f"99acres chunk returned unexpected type: {resp!r}")
                continue
            chunk_leads, error = resp
            if error:
                logger.error(f"99acres chunk error: {error}")
                continue
            all_leads.extend(chunk_leads)

        return all_leads, None

    # ------------------------------------------------------------------ #
    #  Concurrency & retry layers
    # ------------------------------------------------------------------ #

    async def _safe_fetch_chunk(self, *args, **kwargs):
        """Apply semaphore + rate limiter before hitting the circuit breaker."""
        async with _get_semaphore():
            async with _get_limiter():
                return await self._fetch_chunk_protected(*args, **kwargs)

    @acres_breaker
    async def _fetch_chunk_protected(
        self,
        from_date: str,
        to_date: str,
        per_page: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return await self._fetch_chunk_raw(from_date, to_date, per_page)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _fetch_chunk_raw(
        self,
        from_date: str,
        to_date: str,
        per_page: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Raw network call to 99acres Fetch Leads API (paginated)."""
        page = 1
        all_leads: List[Dict[str, Any]] = []

        while True:
            params: Dict[str, Any] = {
                "api_key": self.api_key,
                "from_date": from_date,
                "to_date": to_date,
                "page": page,
                "per_page": per_page,
            }

            logger.info(
                f"99acres API request: from={from_date}, to={to_date}, page={page}"
            )

            try:
                async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                    response = await client.get(self.api_url, params=params)

                    if response.status_code == 200:
                        data = response.json()
                        leads = extract_99acres_leads(data)

                        if not leads:
                            # Empty page → we've exhausted all results
                            break

                        all_leads.extend(leads)

                        # Respect declared total if available
                        total = data.get("total") or data.get("total_count") or 0
                        if total and len(all_leads) >= int(total):
                            break

                        # If we got a full page, fetch next; otherwise we're done
                        if len(leads) < per_page:
                            break

                        page += 1

                    elif response.status_code == 401:
                        logger.error("99acres API: Unauthorized — check ACRES_API_KEY")
                        return [], "Unauthorized (401) — check ACRES_API_KEY"
                    elif response.status_code == 404:
                        # Some accounts may not have pull API enabled
                        logger.warning("99acres API: 404 — pull API may not be enabled for this account")
                        return [], "Pull API not available (404) — contact 99acres account manager"
                    else:
                        logger.error(
                            f"99acres API Error {response.status_code}: {response.text[:500]}"
                        )
                        return [], f"API Error ({response.status_code})"

            except httpx.RequestError as e:
                logger.error(f"99acres API network error: {e}")
                raise  # Let tenacity retry
            except Exception as e:
                logger.error(f"99acres API unexpected error: {e}")
                return [], str(e)

        return all_leads, None

    # ------------------------------------------------------------------ #
    #  Lead mapper: 99acres JSON → internal LeadCreate-compatible dict
    # ------------------------------------------------------------------ #
    @staticmethod
    def map_lead(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a 99acres lead dict to fields compatible with LeadCreate.

        Handles both snake_case and camelCase field names defensively.
        Known fields from 99acres CRM API spec:
            query_id / queryId, name, mobile / phone / contact_number,
            email, city, locality / area, property_type / propertyType,
            budget, project_name / projectName, created_at / createdAt,
            message / query_info
        """

        def _get(*keys: str) -> str:
            """Return the first non-empty value from the raw dict."""
            for k in keys:
                v = raw.get(k)
                if v and str(v).strip():
                    return str(v).strip()
            return ""

        # Phone: try multiple field names
        phone = _get(
            "mobile", "phone", "contact_number", "contactNumber",
            "Mobile", "Phone", "ContactNumber",
        )

        # Location fields
        city = _get("city", "City", "cityName", "city_name")
        locality = _get("locality", "area", "Locality", "Area", "location")

        # Budget
        budget_raw = _get("budget", "Budget", "price", "Price", "budget_range")
        budget = f"₹{budget_raw}" if budget_raw and not budget_raw.startswith("₹") else budget_raw

        # Property type
        prop_type = _get("property_type", "propertyType", "PropertyType", "prod_type", "ProdType")
        requirement = _get("requirement", "query_type", "queryType", "QryType")
        if requirement and requirement.lower() != prop_type.lower():
            prop_type = f"{prop_type} ({requirement})" if prop_type else requirement

        # Project name
        project_name = _get("project_name", "projectName", "ProjectName", "project")

        # Message / query info
        message_parts = []
        query_info = _get("message", "query_info", "queryInfo", "QryInfo", "remarks")
        if query_info:
            message_parts.append(query_info)
        if city:
            message_parts.append(f"City: {city}")
        if locality:
            message_parts.append(f"Locality: {locality}")
        if budget_raw:
            message_parts.append(f"Budget: {budget_raw}")
        if prop_type:
            message_parts.append(f"Type: {prop_type}")

        # Timestamp: created_at / createdAt (epoch int or ISO string)
        lead_date = None
        created_raw = raw.get("created_at") or raw.get("createdAt") or raw.get("lead_date")
        if created_raw:
            try:
                lead_date = int(float(str(created_raw)))
            except (ValueError, TypeError):
                pass

        # External ID
        external_id = _get(
            "query_id", "queryId", "QryId", "qry_id", "id", "lead_id"
        ) or None

        return {
            "name": _get("name", "Name", "lead_name") or None,
            "phone": phone,
            "email": _get("email", "Email", "lead_email") or None,
            "city": city or None,
            "location": locality or city or None,
            "project_name": project_name or None,
            "property_type": prop_type or None,
            "budget": budget or None,
            "message": " | ".join(message_parts) if message_parts else None,
            "lead_date": lead_date,
            "external_id": external_id,
        }

    # ------------------------------------------------------------------ #
    #  Sync: fetch + deduplicate + feed into pipeline
    # ------------------------------------------------------------------ #
    async def sync_leads(
        self,
        from_date: str,
        to_date: str,
        db,
    ) -> Dict[str, Any]:
        """Fetch leads from 99acres, deduplicate, and process via pipeline.

        Returns a summary dict with counts and any errors.
        """
        from app.models.lead import Lead
        from app.schemas.lead import LeadCreate
        from app.services.lead_processor import process_lead

        leads_raw, error = await self.fetch_leads(from_date, to_date)

        if error:
            return {"status": "error", "error": error, "fetched": 0, "imported": 0, "skipped": 0}

        imported: int = 0
        skipped: int = 0
        errors: List[str] = []

        for raw_lead in leads_raw:
            mapped = self.map_lead(raw_lead)
            phone = (mapped.get("phone") or "").strip()

            if len(phone) < 7:
                logger.warning(f"99acres lead skipped — short phone: {phone!r}")
                skipped += 1
                continue

            # Deduplicate: phone + (external_id OR lead_date)
            query = db.query(Lead).filter(
                Lead.phone == phone,
                Lead.source == "99acres",
            )

            ext_id = mapped.get("external_id")
            l_date = mapped.get("lead_date")

            if ext_id and l_date:
                from sqlalchemy import or_
                query = query.filter(
                    or_(Lead.external_id == ext_id, Lead.lead_date == l_date)
                )
            elif ext_id:
                query = query.filter(Lead.external_id == ext_id)
            elif l_date:
                query = query.filter(Lead.lead_date == l_date)

            existing = query.first()
            if existing:
                logger.debug(
                    f"Dedup: 99acres lead phone={phone} already exists (#{existing.id})"
                )
                skipped += 1
                continue

            # Feed into shared pipeline
            try:
                payload = LeadCreate(
                    name=mapped.get("name"),
                    phone=phone,
                    email=mapped.get("email"),
                    city=mapped.get("city"),
                    location=mapped.get("location"),
                    project_name=mapped.get("project_name"),
                    property_type=mapped.get("property_type"),
                    budget=mapped.get("budget"),
                    message=mapped.get("message"),
                    lead_date=mapped.get("lead_date"),
                    external_id=mapped.get("external_id"),
                )
                result = await process_lead(
                    db, payload, "99acres", raw_payload=raw_lead
                )
                if result:
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(f"Failed to process 99acres lead (phone={phone}): {e}")
                errors.append(f"phone={phone}: {str(e)}")

        # Track last sync for health info
        self._last_sync_at = datetime.now()
        self._last_sync_count = imported

        result_summary: Dict[str, Any] = {
            "status": "ok",
            "fetched": len(leads_raw),
            "imported": imported,
            "skipped": skipped,
        }
        if errors:
            result_summary["errors"] = errors[:20]  # cap to avoid huge payloads

        logger.info(f"99acres sync complete: {result_summary}")
        return result_summary


# ---------------------------------------------------------------------------
#  Singleton
# ---------------------------------------------------------------------------
acres_lead_service = AcresLeadService()
