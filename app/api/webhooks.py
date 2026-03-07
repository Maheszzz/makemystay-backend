"""Unified webhook endpoints for external lead-push integrations.

Supports: Housing.com, 99acres, MagicBricks, Meta Ads, Website, Brokers, etc.
All sources hit one parameterized endpoint: POST /webhooks/leads/{source}
"""
import os
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session
from loguru import logger
from typing import Optional, List

from app.configs.db_config import get_mysql_db
from app.schemas.lead import LeadCreate, LeadResponse, LeadWebhookResponse, LeadStatus
from app.repo import lead as lead_repo
from app.utils.zoho_crm_service import zoho_crm_service
from app.api.retell import trigger_outbound_call

webhooks_router = APIRouter(tags=["Webhooks / Leads"])

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


def _get_display_source(source: str) -> str:
    """Return a display-friendly source name for CRM."""
    return SOURCE_DISPLAY_NAMES.get(source.lower(), source.title())


# ------------------------------------------------------------------ #
#  API Key auth
# ------------------------------------------------------------------ #
def _verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Validate the API key sent by the lead source."""
    expected_key = os.getenv("HOUSING_WEBHOOK_API_KEY", "")
    if not expected_key:
        logger.error("HOUSING_WEBHOOK_API_KEY is not configured in environment.")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    if x_api_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ------------------------------------------------------------------ #
#  Adapter: maps LeadCreate → attribute interface for ZohoCRMService
# ------------------------------------------------------------------ #
class _CRMLeadAdapter:
    """Maps a LeadCreate payload to the attribute interface expected by ZohoCRMService."""

    def __init__(self, payload: LeadCreate, source: str):
        self.name_ = payload.name or "Lead"
        self.name = self.name_
        self.phone = payload.phone
        self.email = payload.email or ""
        self.company = "Individual"

        # Combine contextual fields into 'message' for CRM description
        parts = []
        if payload.message:
            parts.append(payload.message)
        if payload.requirement:
            parts.append(f"Requirement: {payload.requirement}")
        if payload.project_name:
            parts.append(f"Project: {payload.project_name}")
        if payload.budget:
            parts.append(f"Budget: {payload.budget}")
        self.message = " | ".join(parts) if parts else ""

        self.location = payload.location or payload.city or ""
        self.property_type = payload.property_type or ""
        self.units = ""
        self.lead_source = _get_display_source(source)


# ================================================================== #
#  POST /webhooks/leads/{source}  —  Universal Lead Webhook
# ================================================================== #
@webhooks_router.post(
    "/webhooks/leads/{source}",
    response_model=LeadWebhookResponse,
    summary="Universal Lead Push Webhook",
)
async def receive_lead(
    source: str,
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_mysql_db),
):
    """
    Receives lead data from any source and processes it through the pipeline:

    1. **Authenticate** via `X-API-Key` header
    2. **Store** in MySQL `leads` table
    3. **Sync** to Zoho CRM (background)
    4. **Trigger AI call** via Retell AI (background, if enabled)

    Path parameter `{source}` identifies the platform:
    `housing`, `99acres`, `magicbricks`, `meta`, `website`, `broker`, etc.
    """
    # --- Auth ---
    _verify_api_key(x_api_key)

    source_normalized = source.lower().strip()
    logger.info(f"Lead webhook [{source_normalized}]: {payload.model_dump()}")

    # --- 1. Combine message fields ---
    combined_message = payload.message or ""
    if payload.requirement:
        combined_message += f" | Requirement: {payload.requirement}" if combined_message else payload.requirement

    # --- 2. Store in MySQL ---
    lead_data = {
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email,
        "source": source_normalized,
        "city": payload.city,
        "location": payload.location,
        "project_name": payload.project_name,
        "property_type": payload.property_type,
        "budget": payload.budget,
        "message": combined_message,
        "status": "new",
        "raw_payload": payload.model_dump(),
    }

    try:
        db_lead = lead_repo.create_lead(db, lead_data)
    except Exception as e:
        logger.error(f"Failed to store lead: {e}")
        raise HTTPException(status_code=500, detail="Failed to store lead")

    # --- 3. Zoho CRM sync (background) ---
    adapter = _CRMLeadAdapter(payload, source_normalized)
    lead_id_ref = db_lead.id  # capture for closure

    async def _sync_to_crm():
        zoho_lead_id = await zoho_crm_service.create_or_update_lead(adapter)
        if zoho_lead_id:
            logger.info(f"Lead #{lead_id_ref} synced to Zoho CRM: {zoho_lead_id}")
            # Update the DB record with Zoho ID
            try:
                from app.configs.db_config import MySQLSessionLocal
                with MySQLSessionLocal() as session:
                    lead_obj = lead_repo.get_lead_by_id(session, lead_id_ref)
                    if lead_obj:
                        lead_repo.update_lead(session, lead_obj, {"zoho_lead_id": zoho_lead_id})
            except Exception as e:
                logger.error(f"Failed to update zoho_lead_id for Lead #{lead_id_ref}: {e}")
        else:
            logger.error(f"Failed to sync Lead #{lead_id_ref} to Zoho CRM")

    background_tasks.add_task(_sync_to_crm)

    # --- 4. AI calling (background, if enabled) ---
    enable_ai_calling = os.getenv("ENABLE_AI_CALLING_FOR_LEADS", "false").lower() == "true"
    if enable_ai_calling:
        background_tasks.add_task(
            trigger_outbound_call,
            name=payload.name or "Customer",
            phone=payload.phone,
            location=payload.location or payload.city or "",
            property_type=payload.property_type or "",
            message=combined_message or "Interested in property",
        )
        # Log call in Zoho CRM
        background_tasks.add_task(zoho_crm_service.log_call, adapter)

    return LeadWebhookResponse(
        status="ok",
        message=f"Lead received from {_get_display_source(source_normalized)} and queued for processing",
        lead_id=db_lead.id,
    )


# ================================================================== #
#  GET /leads  —  List all leads (admin)
# ================================================================== #
@webhooks_router.get(
    "/leads",
    response_model=List[LeadResponse],
    summary="List all leads",
)
def list_leads(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    source: Optional[str] = Query(None, description="Filter by source (housing, 99acres, etc.)"),
    status: Optional[LeadStatus] = Query(None, description="Filter by status"),
    db: Session = Depends(get_mysql_db),
):
    """List all leads with optional source/status filters."""
    return lead_repo.get_leads(
        db,
        skip=skip,
        limit=limit,
        source=source,
        status=status.value if status else None,
    )


# ================================================================== #
#  GET /leads/{lead_id}  —  Single lead detail
# ================================================================== #
@webhooks_router.get(
    "/leads/{lead_id}",
    response_model=LeadResponse,
    summary="Get lead by ID",
)
def get_lead(lead_id: int, db: Session = Depends(get_mysql_db)):
    """Retrieve a single lead by its ID."""
    lead = lead_repo.get_lead_by_id(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
