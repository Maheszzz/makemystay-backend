"""Unified webhook endpoints for external lead-push integrations.

Supports: Housing.com, 99acres, MagicBricks, Meta Ads, Website, Brokers, etc.
All sources hit one parameterized endpoint: POST /webhooks/leads/{source}
"""

import time
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
import hmac
import hashlib
import json
from app.configs.db_config import get_mysql_db, MySQLSessionLocal
from app.core.config import settings
from app.repo import lead as lead_repo
from app.repo.failed_webhook_lead_repo import record_failed_webhook_lead
from app.schemas.lead import LeadCreate, LeadResponse, LeadStatus, LeadWebhookResponse
from app.services.lead_processor import process_lead
from app.core import security
from app.models.zoho_webhook_event import ZohoWebhookEvent

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
#  POST /webhooks/zoho  —  Zoho CRM Bidirectional Sync Receiver
# ================================================================== #
@webhooks_router.post(
    "/webhooks/zoho",
    summary="Zoho CRM Inbound Webhook Receiver",
    description="Captures updates from Zoho CRM with HMAC signature and replay protection."
)
async def receive_zoho_webhook(
    request: Request,
    x_zoho_signature: Optional[str] = Header(None, alias="X-Zoho-Signature"),
    x_zoho_timestamp: Optional[str] = Header(None, alias="X-Zoho-Timestamp")
):
    """
    Receives JSON updates from Zoho:
    
    1. **Verify** HMAC signature using ZOHO_WEBHOOK_SECRET
    2. **Validate** timestamp (5-minute window) for Replay Protection
    3. **Log** event for idempotency & Audit
    """
    body = await request.body()
    
    # 1. Signature & Replay Protection (Elite Hardening)
    if settings.ZOHO_WEBHOOK_SECRET:
        if not x_zoho_signature or not x_zoho_timestamp:
            logger.warning("Zoho Webhook: Missing security headers. Rejecting.")
            raise HTTPException(status_code=401, detail="Missing security headers")
            
        # Replay protection: Reject if more than 5 minutes old
        try:
            ts = float(x_zoho_timestamp)
            if abs(time.time() - ts) > 300:
                logger.warning(f"Zoho Webhook: Replay detected (TS: {ts}). Rejecting.")
                raise HTTPException(status_code=401, detail="Timestamp stale (Replay Protection)")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid timestamp format")

        # HMAC verification
        expected = hmac.new(
            settings.ZOHO_WEBHOOK_SECRET.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(expected, x_zoho_signature):
            logger.warning("Zoho Webhook: Invalid Signature. Rejecting.")
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # event_id is the Zoho Lead ID and potentially a timestamp to distinguish updates
    zoho_id = payload.get("id") or payload.get("LEADID")
    if not zoho_id:
        # Some Zoho alerts don't have IDs in top-level; we log it anyway
        zoho_id = f"Z-{int(time.time())}"

    # Persistent log for idempotency (using MySQLSessionLocal for fast immediate commit)
    with MySQLSessionLocal() as session:
        # Check if already processed (idempotency check)
        existing = session.query(ZohoWebhookEvent).filter(
            ZohoWebhookEvent.event_id == zoho_id,
            ZohoWebhookEvent.status == "processed"
        ).first()
        if existing:
            return {"status": "accepted", "detail": "Already processed"}

        event = ZohoWebhookEvent(
            event_id=str(zoho_id),
            payload=payload,
            status="pending"
        )
        session.add(event)
        session.commit()
        event_db_id = event.id

    # Offload the heavy lifting to Celery
    from app.tasks.zoho_tasks import process_zoho_webhook_task
    process_zoho_webhook_task.delay(event_db_id)

    return {"status": "accepted", "event_id": zoho_id}


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
    db: Session = Depends(get_mysql_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, description="API Key via query param"),
):
    """
    Receives an XML payload of multiple leads from 99acres and returns an
    XML response. Expects API Key via ``api_key`` query parameter or
    ``X-API-Key`` header.

    Per-``Qry`` failures are stored in ``failed_webhook_leads`` and return
    ``status`` **N** (not Y) so the portal does not treat them as accepted.
    Set ``WEBHOOK_99ACRES_HTTP_500_ON_ANY_QRY_FAILURE=true`` to also fail the
    HTTP response so the provider may retry the batch.
    """
    _verify_api_key(x_api_key, api_key)

    body = await request.body()
    max_log = getattr(settings, "WEBHOOK_LOG_BODY_MAX", 50_000) or 0
    if max_log > 0:
        preview = body[:max_log].decode("utf-8", errors="replace")
        logger.info(
            "99acres webhook: raw_bytes={} preview={}",
            len(body),
            preview,
        )
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        logger.error("Failed to parse 99acres XML: {}", e)
        return Response(
            content="<xml><error>Invalid XML</error></xml>",
            media_type="application/xml",
            status_code=400,
        )

    qry_nodes = root.findall("Qry")
    if not qry_nodes:
        logger.warning("99acres webhook: parsed XML but no <Qry> elements")
        return Response(
            content="<xml><error>No Qry elements</error></xml>",
            media_type="application/xml",
            status_code=400,
        )

    resp_root = ET.Element("xml")
    any_qry_failed = False

    for qry in qry_nodes:
        qry_id_elem = qry.find("QryId")
        qry_id = qry_id_elem.text.strip() if qry_id_elem is not None and qry_id_elem.text else ""
        
        # 99acres often sends empty <QryId />. We should still process the lead.
        effective_qry_id = qry_id or f"99-{int(time.time())}"
        
        lead_data = AcersAdapter.to_lead_create(qry)
        if lead_data and not lead_data.external_id:
            lead_data.external_id = effective_qry_id

        if not lead_data:
            any_qry_failed = True
            err = "missing_or_invalid_phone_after_field_mapping"
            logger.error("99acres QryId={} — {}, dead-letter stored", effective_qry_id, err)
            try:
                record_failed_webhook_lead(
                    db,
                    source="99acres",
                    external_ref=effective_qry_id,
                    payload=AcersAdapter.qry_xml_string(qry),
                    error=err,
                )
            except Exception as ex:
                logger.error("failed_webhook_leads insert: {}", ex)
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id or "UNKNOWN"
            ET.SubElement(resp_qry, "status").text = "N"
            continue

        try:
            from app.tasks.webhook_tasks import process_webhook_lead_task

            process_webhook_lead_task.delay("99acres", lead_data.model_dump())

            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id or "UNKNOWN"
            ET.SubElement(resp_qry, "status").text = "Y"
        except Exception as e:
            any_qry_failed = True
            logger.error("Failed to enqueue 99acres lead {}: {}", effective_qry_id, e)
            try:
                record_failed_webhook_lead(
                    db,
                    source="99acres",
                    external_ref=effective_qry_id,
                    payload=AcersAdapter.qry_xml_string(qry),
                    error=f"enqueue_failed: {e}",
                )
            except Exception as ex:
                logger.error("failed_webhook_leads insert: {}", ex)
            resp_qry = ET.SubElement(resp_root, "QryResp")
            ET.SubElement(resp_qry, "QryId").text = qry_id or "UNKNOWN"
            ET.SubElement(resp_qry, "status").text = "N"

    xml_out = ET.tostring(resp_root, encoding="utf-8", xml_declaration=False)
    if any_qry_failed and getattr(settings, "WEBHOOK_99ACRES_HTTP_500_ON_ANY_QRY_FAILURE", False):
        return Response(content=xml_out, media_type="application/xml", status_code=500)
    return Response(content=xml_out, media_type="application/xml")


# ================================================================== #
#  GET /webhooks/lead-list  —  Repo-based lead listing (filters)
#  NOTE: Do not use GET /leads here — that path is reserved for CRM (role-based) in admin/crm.py
# ================================================================== #
@webhooks_router.get(
    "/webhooks/lead-list",
    response_model=List[LeadResponse],
    summary="List leads (repo filters; use GET /leads for CRM role-based list)",
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
