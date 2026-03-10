"""Unified webhook endpoints for external lead-push integrations.

Supports: Housing.com, 99acres, MagicBricks, Meta Ads, Website, Brokers, etc.
All sources hit one parameterized endpoint: POST /webhooks/leads/{source}
"""
import os
import xml.etree.ElementTree as ET
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks, Depends, Query, Request, Response
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
def _verify_api_key(x_api_key: Optional[str], api_key: Optional[str]):
    """Validate the API key sent by the lead source."""
    key_to_check = x_api_key or api_key
    if not key_to_check:
        raise HTTPException(status_code=401, detail="Missing API key")

    expected_key = os.getenv("HOUSING_WEBHOOK_API_KEY", "")
    if not expected_key:
        logger.error("HOUSING_WEBHOOK_API_KEY is not configured in environment.")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    if key_to_check != expected_key:
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


# ------------------------------------------------------------------ #
#  Shared Lead Pipeline
# ------------------------------------------------------------------ #
def _process_lead_pipeline(
    source: str,
    payload: LeadCreate,
    background_tasks: BackgroundTasks,
    db: Session,
):
    source_normalized = source.lower().strip()
    logger.info(f"Lead pipeline [{source_normalized}]: {payload.model_dump()}")

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

    return db_lead


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
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, description="API Key via query param"),
    db: Session = Depends(get_mysql_db),
):
    """
    Receives lead data from any source and processes it through the pipeline:

    1. **Authenticate** via `X-API-Key` header or `api_key` param
    2. **Store** in MySQL `leads` table
    3. **Sync** to Zoho CRM (background)
    4. **Trigger AI call** via Retell AI (background, if enabled)

    Path parameter `{source}` identifies the platform:
    `housing`, `99acres`, `magicbricks`, `meta`, `website`, `broker`, etc.
    """
    _verify_api_key(x_api_key, api_key)

    db_lead = _process_lead_pipeline(source, payload, background_tasks, db)

    return LeadWebhookResponse(
        status="ok",
        message=f"Lead received from {_get_display_source(source)} and queued for processing",
        lead_id=db_lead.id,
    )


# ================================================================== #
#  POST /webhooks/99acres  —  99acres Bulk XML Webhook
# ================================================================== #
@webhooks_router.post(
    "/webhooks/99acres",
    summary="99acres XML Push Integration",
)
async def receive_99acres_xml(
    request: Request,
    background_tasks: BackgroundTasks,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, description="API Key via query param"),
    db: Session = Depends(get_mysql_db),
):
    """
    Receives an XML payload of multiple leads from 99acres and returns an XML response.
    Expects API Key via `api_key` query parameter or `X-API-Key` header.
    """
    _verify_api_key(x_api_key, api_key)

    body = await request.body()
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        logger.error(f"Failed to parse 99acres XML: {e}")
        return Response(content="<xml><error>Invalid XML</error></xml>", media_type="application/xml", status_code=400)

    # Build response XML
    resp_root = ET.Element("xml")

    # Process each query
    for qry in root.findall("Qry"):
        def _get_text(tag: str) -> str:
            elem = qry.find(tag)
            return elem.text if elem is not None and elem.text else ""

        qry_id = _get_text("QryId")
        if not qry_id:
            continue

        phone = _get_text("Phone")
        if not phone:
            logger.warning(f"99acres lead {qry_id} has no phone number, skipping.")
            # Still acknowledge with Y to prevent retries
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id
            ET.SubElement(resp_qry, "status").text = "Y"
            continue

        project_parts = []
        project_val = _get_text("Project")
        if project_val:
            project_parts.append(f"Project ID: {project_val}")
        cmpct_val = _get_text("CmpctLabl")
        if cmpct_val:
            project_parts.append(cmpct_val)

        payload = LeadCreate(
            name=_get_text("Name"),
            email=_get_text("Email"),
            phone=phone,
            message=_get_text("QryInfo"),
            project_name=" | ".join(project_parts) if project_parts else None,
        )

        # Catch specific failures and mark "N" in return XML only for error logic
        try:
            _process_lead_pipeline("99acres", payload, background_tasks, db)
            
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id
            ET.SubElement(resp_qry, "status").text = "Y"
        except Exception as e:
            logger.error(f"Failed to process 99acres lead {qry_id}: {e}")
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id
            ET.SubElement(resp_qry, "status").text = "N"

    return Response(
        content=ET.tostring(resp_root, encoding="utf-8", xml_declaration=False), 
        media_type="application/xml"
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
