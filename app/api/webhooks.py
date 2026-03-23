"""Unified webhook endpoints for external lead-push integrations.

Supports: Housing.com, 99acres, MagicBricks, Meta Ads, Website, Brokers, etc.
All sources hit one parameterized endpoint: POST /webhooks/leads/{source}
"""

import xml.etree.ElementTree as ET
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from loguru import logger
from sqlalchemy.orm import Session

from app.adapters.acers_adapter import AcersAdapter
from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.repo import lead as lead_repo
from app.schemas.lead import LeadCreate, LeadResponse, LeadStatus, LeadWebhookResponse
from app.services.lead_processor import process_lead
from app.core import security

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
    """Feed a lead through the centralized processor."""
    source_normalized = source.lower().strip()
    return await process_lead(
        db, payload, source_normalized, raw_payload=payload.model_dump()
    )


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
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, description="API Key via query param"),
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

    # 100% production-ready: Enqueue to background worker instantly
    from app.tasks.webhook_tasks import process_webhook_lead_task
    process_webhook_lead_task.delay(source, payload.model_dump())

    return LeadWebhookResponse(
        status="ok",
        message=(
            f"Lead received from {_get_display_source(source)} "
            "and queued for processing"
        ),
        lead_id=0,
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
            "message": "Send POST with XML payload to ingest leads.",
        }
    except HTTPException as e:
        return {"status": "reachable", "auth": "failed", "detail": e.detail}


@webhooks_router.post(
    "/webhooks/99acres",
    summary="99acres XML Push Integration",
)
async def receive_99acres_xml(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, description="API Key via query param"),
):
    """
    Receives an XML payload of multiple leads from 99acres and returns an
    XML response. Expects API Key via ``api_key`` query parameter or
    ``X-API-Key`` header.
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

    for qry in root.findall("Qry"):
        qry_id_elem = qry.find("QryId")
        qry_id = qry_id_elem.text if qry_id_elem is not None and qry_id_elem.text else ""
        if not qry_id:
            continue

        # Use the adapter to convert XML → LeadCreate
        lead_data = AcersAdapter.to_lead_create(qry)

        if not lead_data:
            logger.warning(f"99acres lead {qry_id} has no phone number, skipping.")
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id
            ET.SubElement(resp_qry, "status").text = "Y"
            continue

        try:
            from app.tasks.webhook_tasks import process_webhook_lead_task
            process_webhook_lead_task.delay("99acres", lead_data.model_dump())
            
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id
            ET.SubElement(resp_qry, "status").text = "Y"
        except Exception as e:
            logger.error(f"Failed to enqueue 99acres lead {qry_id}: {e}")
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
    assigned_to: Optional[int] = Query(
        None, description="Filter by assigned agent ID"
    ),
    db: Session = Depends(get_mysql_db),
    current_user=Depends(security.get_current_user),
):
    """List all leads with optional source/status/agent filters."""
    return lead_repo.get_leads(
        db,
        skip=skip,
        limit=limit,
        source=source,
        status=status.value if status else None,
        assigned_to=assigned_to,
    )


# ================================================================== #
#  GET /leads/{lead_id}  —  Single lead detail
# ================================================================== #
@webhooks_router.get(
    "/leads/{lead_id}",
    response_model=LeadResponse,
    summary="Get lead by ID",
)
def get_lead(lead_id: int, db: Session = Depends(get_mysql_db), current_user=Depends(security.get_current_user)):
    """Retrieve a single lead by its ID."""
    lead = lead_repo.get_lead_by_id(db, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
