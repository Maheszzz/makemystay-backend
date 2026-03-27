"""Retell AI API endpoints for creating web calls and outbound phone calls."""

import json
import re
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field

from app.core.config import settings
from app.configs.db_config import get_mysql_db
from app.core import security
from app.models.retell_call import RetellCall
from sqlalchemy.orm import Session

retell_router = APIRouter(tags=["Retell AI"])

RETELL_API_KEY = settings.RETELL_API_KEY
RETELL_AGENT_ID = settings.RETELL_AGENT_ID
RETELL_FROM_NUMBER = settings.RETELL_FROM_NUMBER
RETELL_API_BASE = "https://api.retellai.com"


# -----------------------------------------
# Create Web Call (Browser Voice Call)
# -----------------------------------------
@retell_router.post("/retell/create-web-call")
async def create_web_call():
    """
    Creates a web call token for browser voice calls.
    """

    if not RETELL_API_KEY:
        raise HTTPException(status_code=500, detail="RETELL_API_KEY not configured")

    if not RETELL_AGENT_ID:
        raise HTTPException(status_code=500, detail="RETELL_AGENT_ID not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{RETELL_API_BASE}/v2/create-web-call",
                headers={
                    "Authorization": f"Bearer {RETELL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={"agent_id": RETELL_AGENT_ID},
                timeout=10.0,
            )

            response.raise_for_status()

            data = response.json()

            logger.info("Retell web call created successfully")

            return {"access_token": data["access_token"]}

    except httpx.HTTPStatusError as e:
        logger.error(f"Retell API error: {e.response.text}")
        raise HTTPException(
            status_code=e.response.status_code, detail="Retell API error"
        )

    except httpx.RequestError as e:
        logger.error(f"Network error contacting Retell: {str(e)}")
        raise HTTPException(status_code=503, detail="Retell API unavailable")


# -----------------------------------------
# Phone Formatting Helper
# -----------------------------------------
def format_phone_number(phone: str) -> str:
    """
    Format phone number to E.164 format.
    Defaults to India (+91) if 10 digit number.
    """

    phone = phone.strip().replace(" ", "")

    if phone.startswith("+"):
        return phone

    if len(phone) == 10 and phone.isdigit():
        return f"+91{phone}"

    if phone.startswith("91") and len(phone) == 12:
        return f"+{phone}"

    return f"+{phone}"


# -----------------------------------------
# Trigger Outbound AI Call
# -----------------------------------------
async def trigger_outbound_call(
    name: str,
    phone: str,
    location: str = "",
    property_type: str = "",
    message: str = "",
    test_id: Optional[int] = None,
    contact_id: Optional[int] = None,
    lead_id: Optional[int] = None,
    project: Optional[str] = None,
):
    """
    Trigger outbound AI call using Retell.

    This call will follow the Maya conversation script
    configured inside the Retell Agent prompt.
    """

    if not RETELL_API_KEY or not RETELL_AGENT_ID:
        logger.error("Retell config missing, skipping outbound call")
        return

    formatted_phone = format_phone_number(phone)

    logger.info(f"Triggering AI call to {formatted_phone} ({name})")

    payload = {
        "from_number": RETELL_FROM_NUMBER,
        "to_number": formatted_phone,
        "agent_id": RETELL_AGENT_ID,
        "metadata": {
            "test_id": test_id,
            "contact_id": contact_id,
            "lead_id": lead_id,
        },
        "retell_llm_dynamic_variables": {
            "name": name,
            "location": location,
            "property_type": property_type or project or "",
            "requirement": message or "interested in property options",
            "test_id": str(test_id) if test_id is not None else "",
            "lead_id": str(lead_id) if lead_id is not None else "",
        },
    }

    try:
        async with httpx.AsyncClient() as client:

            response = await client.post(
                f"{RETELL_API_BASE}/v2/create-phone-call",
                headers={
                    "Authorization": f"Bearer {RETELL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=15.0,
            )

            if response.status_code != 201:
                logger.error(
                    f"Retell call failed: {response.status_code} - {response.text}"
                )
                return

            data = response.json()

            logger.success(f"Outbound call started: {data.get('call_id')}")
            return data

    except httpx.RequestError as e:
        logger.error(f"Network error triggering call: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error triggering call: {str(e)}")
    return None

# -----------------------------------------
# Retell Webhook (Status / Call Events)
# -----------------------------------------
@retell_router.post("/retell/webhook")
async def retell_webhook(request: Request, db: Session = Depends(get_mysql_db)):
    """
    Receives call status updates and events from Retell AI.
    Configure this URL in the Retell Dashboard as the 'Webhook URL'.
    """
    try:
        payload = await request.json()
        event = payload.get("event")
        call_id = payload.get("call_id")

        logger.info(f"Retell Webhook: event={event}, call_id={call_id}")
        logger.debug(f"Retell Webhook Payload: {payload}")

        if not call_id:
            return {"status": "ok"}

        # Only update test rows when the webhook matches a known call_id.
        test_row = (
            db.query(RetellCall).filter(RetellCall.retell_call_id == call_id).first()
        )
        if not test_row:
            return {"status": "ok", "reason": "no_matching_test_row"}

        # Best-effort transcript extraction
        def _find_transcript(obj: Any) -> Optional[Any]:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    if "transcript" in lk or "transcription" in lk:
                        if isinstance(v, (str, dict, list)):
                            return v
                    found = _find_transcript(v)
                    if found is not None:
                        return found
            elif isinstance(obj, list):
                for item in obj:
                    found = _find_transcript(item)
                    if found is not None:
                        return found
            return None

        transcript = (
            payload.get("transcript")
            or payload.get("transcription")
            or payload.get("call_transcript")
            or payload.get("callTranscript")
            or _find_transcript(payload)
            or ""
        )
        if isinstance(transcript, (dict, list)):
            transcript = json.dumps(transcript)
        transcript_str = str(transcript)

        # Update raw payload + status
        # `raw_webhook_payload` is a JSON column; store the parsed payload object.
        test_row.raw_webhook_payload = payload
        ev = (event or "").lower()
        if "no_answer" in ev:
            test_row.status = "no_answer"
        elif "failed" in ev or "error" in ev:
            test_row.status = "failed"
        else:
            test_row.status = "called"  # Updated according to spec

        # Parse SUMMARY line if present:
        # SUMMARY: interested=<true|false>, location=<...>, budget=<...>, move_in=<...>
        interested: Optional[bool] = None
        location: Optional[str] = None
        budget: Optional[str] = None
        move_in: Optional[str] = None

        summary_match = re.search(
            r"SUMMARY:\s*interested\s*=\s*(true|false)\s*,\s*location\s*=\s*(.*?)\s*,\s*budget\s*=\s*(.*?)\s*,\s*move_in\s*=\s*(.*)$",
            transcript_str,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if summary_match:
            interested = summary_match.group(1).lower() == "true"
            location = summary_match.group(2).strip()
            budget = summary_match.group(3).strip()
            move_in = summary_match.group(4).strip()
        else:
            # Fallback to simpler extraction
            it = re.search(r"interested\s*=\s*(true|false)", transcript_str, flags=re.I)
            if it:
                interested = it.group(1).lower() == "true"
            loc = re.search(r"location\s*=\s*([^,]+)", transcript_str, flags=re.I)
            bd = re.search(r"budget\s*=\s*([^,]+)", transcript_str, flags=re.I)
            mv = re.search(r"move_in\s*=\s*(.+)$", transcript_str, flags=re.I | re.DOTALL)
            if loc:
                location = loc.group(1).strip()
            if bd:
                budget = bd.group(1).strip()
            if mv:
                move_in = mv.group(1).strip()

        if test_row.contact_id:
            from app.models.realty import Contact
            contact = db.query(Contact).filter(Contact.id == test_row.contact_id).first()
            if contact:
                contact.is_ai_called = True
                contact.call_status = test_row.status
                if interested is not None:
                    contact.interested = interested
                if budget:
                    contact.budget = budget
                if location:
                    contact.location = location

        if test_row.lead_id:
            from app.models.lead import Lead
            lead = db.query(Lead).filter(Lead.id == test_row.lead_id).first()
            if lead:
                lead.is_ai_called = True
                if interested is True:
                    lead.lead_stage = "interested"
                elif interested is False:
                    lead.lead_stage = "not_interested"
                
                if location:
                    lead.location = location
        # SUMMARY: interested=<true|false>, location=<...>, budget=<...>, move_in=<...>
        interested: Optional[bool] = None
        location: Optional[str] = None
        budget: Optional[str] = None
        move_in: Optional[str] = None

        summary_match = re.search(
            r"SUMMARY:\s*interested\s*=\s*(true|false)\s*,\s*location\s*=\s*(.*?)\s*,\s*budget\s*=\s*(.*?)\s*,\s*move_in\s*=\s*(.*)$",
            transcript_str,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if summary_match:
            interested = summary_match.group(1).lower() == "true"
            location = summary_match.group(2).strip()
            budget = summary_match.group(3).strip()
            move_in = summary_match.group(4).strip()
        else:
            # Fallback to simpler extraction
            it = re.search(r"interested\s*=\s*(true|false)", transcript_str, flags=re.I)
            if it:
                interested = it.group(1).lower() == "true"
            loc = re.search(r"location\s*=\s*([^,]+)", transcript_str, flags=re.I)
            bd = re.search(r"budget\s*=\s*([^,]+)", transcript_str, flags=re.I)
            mv = re.search(r"move_in\s*=\s*(.+)$", transcript_str, flags=re.I | re.DOTALL)
            if loc:
                location = loc.group(1).strip()
            if bd:
                budget = bd.group(1).strip()
            if mv:
                move_in = mv.group(1).strip()

        if transcript_str:
            test_row.transcript = transcript_str
        test_row.summary_interested = interested
        test_row.summary_location = location
        test_row.summary_budget = budget
        test_row.summary_move_in = move_in

        db.commit()

        # Trigger Zoho CRM sync for the contact to update AI tags
        if test_row.lead_id:
            try:
                from app.tasks.lead_tasks import sync_lead_to_zoho_task
                sync_lead_to_zoho_task.delay(test_row.lead_id)
            except Exception as e:
                logger.error(f"Failed to trigger Zoho sync for lead after AI call: {e}")

        return {"status": "updated"}

    except Exception as e:
        logger.error(f"Error processing Retell webhook: {str(e)}")
        # Return 200 anyway to avoid Retell retries if the error is on our side or payload format
        return {"status": "error", "message": str(e)}


class TriggerRetellTestCallsRequest(BaseModel):
    limit: int = 5

@retell_router.post(
    "/retell/test-calls/trigger",
    summary="Trigger queued Retell test calls from retell_call_tests",
)
async def trigger_retell_test_calls(
    req: TriggerRetellTestCallsRequest,
    db: Session = Depends(get_mysql_db),
    _admin=Depends(security.admin_required),
):
    tests = (
        db.query(RetellCall)
        .filter(RetellCall.status == "queued", RetellCall.retell_call_id.is_(None))
        .limit(req.limit)
        .all()
    )

    if not tests:
        return {"status": "ok", "triggered": 0, "reason": "no_queued_tests"}

    triggered = 0
    for row in tests:
        try:
            row.status = "calling"
            db.commit()

            data = await trigger_outbound_call(
                name="Test",
                phone=row.to_phone,
                location="",
                property_type="",
                message="interested in property options",
                test_id=row.id,
            )
            if not data:
                row.status = "failed"
                db.commit()
                continue

            call_id = data.get("call_id") or data.get("id")
            row.retell_call_id = call_id
            row.status = "calling"
            db.commit()
            triggered += 1
        except Exception as e:
            logger.error(f"Failed to trigger test call row_id={row.id}: {e}")
            row.status = "failed"
            db.commit()

    return {"status": "ok", "triggered": triggered, "total_found": len(tests)}
