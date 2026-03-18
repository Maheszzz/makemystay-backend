"""Unified webhook endpoints for external lead-push integrations.

Supports: Housing.com, 99acres, MagicBricks, Meta Ads, Website, Brokers, etc.
All sources hit one parameterized endpoint: POST /webhooks/leads/{source}
"""

import os
import xml.etree.ElementTree as ET
from typing import List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from loguru import logger
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.repo import lead as lead_repo
from app.schemas.lead import LeadCreate, LeadResponse, LeadStatus, LeadWebhookResponse
from app.utils.zoho_crm_service import _get_display_source
from app.services.lead_processor import process_lead

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

    expected_key = settings.HOUSING_WEBHOOK_API_KEY
    if not expected_key:
        logger.error("HOUSING_WEBHOOK_API_KEY is not configured in settings.")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    if key_to_check != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# ------------------------------------------------------------------ #
#  Shared Lead Pipeline
# ------------------------------------------------------------------ #
async def _process_lead_pipeline(
    source: str,
    payload: LeadCreate,
    db: Session,
):
    """Refactored to use centralized lead_processor."""
    source_normalized = source.lower().strip()
    return await process_lead(db, payload, source_normalized, raw_payload=payload.model_dump())


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

    db_lead = await _process_lead_pipeline(source, payload, db)
    if not db_lead:
        # Fallback for duplicates if needed (process_lead returns None for dups)
        return LeadWebhookResponse(status="skipped", message="Duplicate lead detected")

    return LeadWebhookResponse(
        status="ok",
        message=f"Lead received from {_get_display_source(source)} and queued for processing",
        lead_id=db_lead.id,
    )


# ================================================================== #
#  POST /webhooks/99acres  —  99acres Bulk XML Webhook
# ================================================================== #
@webhooks_router.get(
    "/webhooks/99acres",
    summary="Diagnostic for 99acres Webhook",
)
async def test_99acres_webhook(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
):
    """Simple GET endpoint for IT teams to verify that the webhook is reachable."""
    try:
        _verify_api_key(x_api_key, api_key)
        return {
            "status": "active",
            "endpoint": "99acres XML Webhook",
            "auth": "verified",
            "message": "Send POST with XML payload to ingest leads."
        }
    except HTTPException as e:
        return {
            "status": "reachable",
            "auth": "failed",
            "detail": e.detail
        }


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
        return Response(
            content="<xml><error>Invalid XML</error></xml>",
            media_type="application/xml",
            status_code=400,
        )

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
        # Support both 'Project' (generic) and 'ProjectName' / 'ProjectCode' (specific to 99acres XML)
        p_name = _get_text("ProjectName")
        p_code = _get_text("ProjectCode")
        p_generic = _get_text("Project")
        
        if p_name:
            project_parts.append(p_name)
        if p_code:
            project_parts.append(f"Code: {p_code}")
        if not p_name and p_generic:
            project_parts.append(p_generic)
            
        cmpct_val = _get_text("CmpctLabl")
        if cmpct_val:
            project_parts.append(f"[{cmpct_val}]")

        payload = LeadCreate(
            name=_get_text("Name") or "User",
            email=_get_text("Email"),
            phone=phone,
            message=_get_text("QryInfo"),
            project_name=" | ".join(project_parts) if project_parts else None,
        )

        # Catch specific failures and mark "N" in return XML only for error logic
        try:
            await _process_lead_pipeline("99acres", payload, db)

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
        media_type="application/xml",
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
    source: Optional[str] = Query(
        None, description="Filter by source (housing, 99acres, etc.)"
    ),
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
