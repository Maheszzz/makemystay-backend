from __future__ import annotations

from app.schemas.whatsapp_lead import WhatsAppWidgetLeadCreate, WhatsAppWidgetLeadResponse

import json
import re
import time
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Header
from fastapi.responses import PlainTextResponse
from loguru import logger
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.core.redis import redis_conn
from app.events.event_service import publish_event
from app.models.agent import Agent
from app.models.lead import Lead
from app.repo import agent_repo
from app.repo import lead as lead_repo
from app.services.assignment_service import assign_lead
from app.services.whatsapp_service import send_template_whatsapp, send_text_whatsapp
from app.models.retell_call import RetellCall
from app.api.retell import trigger_outbound_call
import asyncio
from app.configs.db_config import SessionLocal

async def _trigger_and_save_call(phone: str, lead_id: int, message: str):
    with SessionLocal() as db_bg:
        rc = RetellCall(
            lead_id=lead_id,
            to_phone=phone,
            status="queued"
        )
        db_bg.add(rc)
        db_bg.commit()
        db_bg.refresh(rc)
        
        data = await trigger_outbound_call(
            name="Customer",
            phone=phone,
            message=message,
            test_id=rc.id
        )
        
        if data and data.get("call_id"):
            rc.retell_call_id = data.get("call_id")
            rc.status = "calling"
        else:
            rc.status = "failed"
        db_bg.commit()


whatsapp_router = APIRouter(tags=["WhatsApp"])


# WhatsApp customer-care window is 24 hours since the user's last inbound message.
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24 hours
SOURCE = "whatsapp"


def _normalize_from_twilio(from_value: str) -> str:
    raw = (from_value or "").strip()
    if raw.startswith("whatsapp:"):
        raw = raw.replace("whatsapp:", "", 1)
    return raw


def _sess_key(phone: str) -> str:
    return f"wa:flow:{phone}"


def _get_session(phone: str) -> Dict[str, Any]:
    if not redis_conn:
        return {}
    try:
        val = redis_conn.get(_sess_key(phone))
        if not val:
            return {}
    except Exception as e:
        logger.error(f"Redis get session failed for {phone}: {e}")
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def _set_session(phone: str, data: Dict[str, Any]) -> None:
    if not redis_conn:
        return
    try:
        redis_conn.setex(_sess_key(phone), SESSION_TTL_SECONDS, json.dumps(data))
    except Exception as e:
        logger.error(f"Redis set session failed for {phone}: {e}")


def _clear_session(phone: str) -> None:
    if not redis_conn:
        return
    try:
        redis_conn.delete(_sess_key(phone))
    except Exception as e:
        logger.error(f"Redis delete session failed for {phone}: {e}")


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _normalize_msg(msg: str) -> str:
    """
    Light normalization so users can type text instead of only 1/2/3.
    """
    b = _clean_text(msg).lower()
    b = b.replace("one bhk", "1bhk").replace("two bhk", "2bhk").replace("three bhk", "3bhk")
    if "not interested" in b:
        return "2"
    if b in {"yes", "y", "interested", "ok"}:
        return "1"
    if b in {"no", "n", "nope"}:
        return "2"
    return b


def _parse_yes_no(body: str) -> Optional[bool]:
    b = _normalize_msg(body)
    if b in {"1", "yes", "y", "interested", "ok"}:
        return True
    if b in {"2", "no", "n", "not interested", "nope"}:
        return False
    return None


PROPERTY_TYPE_MAP = {
    "1": "PG",
    "2": "1BHK",
    "3": "2BHK",
    "4": "3BHK",
    "5": "Other",
}


def _parse_property_type(body: str) -> Optional[str]:
    b = _normalize_msg(body)
    if b in PROPERTY_TYPE_MAP:
        return PROPERTY_TYPE_MAP[b]
    # allow direct strings
    b2 = b.upper().replace(" ", "")
    if b2 in {"PG", "1BHK", "2BHK", "3BHK"}:
        return b2
    return None


def _parse_move_in(body: str) -> Optional[str]:
    b = _normalize_msg(body)
    if b in {"1", "immediate", "now", "asap"}:
        return "immediate"
    if b in {"2", "custom", "date", "later"}:
        return "custom"
    return None


def _parse_date(body: str) -> Optional[str]:
    b = _clean_text(body)
    # Expect YYYY-MM-DD
    try:
        dt = datetime.strptime(b, "%Y-%m-%d")
        return dt.date().isoformat()
    except Exception:
        return None


def _upsert_lead(db: Session, phone: str, updates: Dict[str, Any]) -> int:
    existing = lead_repo.get_lead_by_phone_source(db, phone=phone, source=SOURCE)
    if existing:
        lead_repo.update_lead(db, existing, updates)
        return existing.id
    created = lead_repo.create_lead(
        db,
        {
            "phone": phone,
            "source": SOURCE,
            "status": "new",
            **updates,
        },
    )
    return created.id


def _update_lead_by_id(db: Session, lead_id: int, updates: Dict[str, Any]) -> None:
    obj = lead_repo.get_lead_by_id(db, lead_id)
    if not obj:
        return
    lead_repo.update_lead(db, obj, updates)
    
    # Elite Tier: Event-driven Zoho sync on any detailed update
    try:
        from app.tasks.lead_tasks import sync_lead_to_zoho_task
        sync_lead_to_zoho_task.delay(lead_id)
    except Exception as e:
        logger.error(f"Failed to trigger sync after lead update: {e}")


def _merge_raw_payload(existing: Optional[dict], patch: Dict[str, Any]) -> Dict[str, Any]:
    base = existing if isinstance(existing, dict) else {}
    merged = {**base}
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**merged[k], **v}
        else:
            merged[k] = v
    return merged


def _assign_rm(db: Session, lead_id: int) -> Optional[Agent]:
    """
    Transactional RM assignment using SELECT FOR UPDATE on agents,
    reusing the same logic as the ingestion pipeline.
    """
    lead_obj: Optional[Lead] = lead_repo.get_lead_by_id(db, lead_id)
    if not lead_obj:
        return None

    try:
        agents = agent_repo.get_available_agents_for_update(db, location=lead_obj.location)
        assigned = assign_lead(lead_obj, agents)
        if not assigned:
            publish_event(lead_id, "UNASSIGNED", "No available agents for assignment")
            db.commit()
            return None

        lead_obj.assigned_to = assigned.id
        assigned.current_load = assigned.current_load + 1
        db.commit()
        publish_event(lead_id, "ASSIGNED", f"Assigned to agent {assigned.name}")
        return assigned
    except Exception as e:
        logger.error(f"RM assignment failed for lead {lead_id}: {e}")
        db.rollback()
        return None


def _ask_interest(name: Optional[str] = None) -> str:
    nm = f" {name}" if name else ""
    return (
        f"Hi{nm}! Thanks for reaching out.\n\n"
        "Are you interested in getting property options?\n"
        "Reply:\n"
        "1) Interested\n"
        "2) Not Interested"
    )


def _ask_property_type() -> str:
    return (
        "Great.\n\nWhich type are you looking for?\n"
        "Reply:\n"
        "1) PG\n"
        "2) 1 BHK\n"
        "3) 2 BHK\n"
        "4) 3 BHK\n"
        "5) Other"
    )


def _ask_location() -> str:
    return "Which location do you prefer? (Example: BTM Layout / HSR / Whitefield)"


def _ask_move_in() -> str:
    return (
        "Move-in timeline?\n"
        "Reply:\n"
        "1) Immediate\n"
        "2) Choose a date"
    )


def _ask_date() -> str:
    return "Please reply with your move-in date in this format: YYYY-MM-DD"


def _final_message() -> str:
    return "Perfect — thanks! Our RM will contact you shortly."


def _final_message_with_rm(rm: Optional[Agent]) -> str:
    if not rm:
        return (
            "Perfect — thanks! 🎉\n\n"
            "Our RM will contact you shortly.\n"
            "Have a great day!"
        )
    return (
        "Perfect — thanks! 🎉\n\n"
        f"Our RM {rm.name} will contact you shortly.\n"
        f"📞 {rm.phone}\n\n"
        "Have a great day!"
    )


def _default_session(lead_id: int) -> Dict[str, Any]:
    return {
        "step": "interest",
        "lead_id": lead_id,
        # Timestamp (unix seconds) of the most recent inbound message.
        # Used to stay aligned with WhatsApp customer-care (24h) rules.
        "last_inbound_at": 0,
        "data": {
            "interest": "",
            "property_type": "",
            "location": "",
            "move_in": "",
            "move_in_date": "",
        },
    }


def _send_text_checked(*, to: str, body: str) -> None:
    """
    Send a free-form WhatsApp message and log Twilio failure details.
    Helps when you locally "replay" webhook payloads and nothing arrives.
    """
    def _is_transient(err: Optional[str]) -> bool:
        e = (err or "").lower()
        return any(
            key in e
            for key in [
                "timeout",
                "max retries exceeded",
                "connection",
                "failed to establish a new connection",
                "temporarily unavailable",
            ]
        )

    def _is_outside_customer_care(err: Optional[str]) -> bool:
        e = (err or "").lower()
        return any(
            key in e
            for key in [
                "24 hour",
                "24-hour",
                "customer care",
                "care window",
                "outside",
            ]
        )

    last_err: Optional[str] = None
    for attempt in range(3):
        res = send_text_whatsapp(to=to, body=body)
        if getattr(res, "ok", False):
            return

        last_err = getattr(res, "error", None)
        logger.error(
            "Twilio text send failed",
            to=to,
            body=body,
            attempt=attempt + 1,
            error=last_err,
        )

        if attempt < 2 and _is_transient(last_err):
            time.sleep(1 * (attempt + 1))

    # Free-form can be blocked outside WhatsApp customer-care window.
    fallback_sid = settings.TWILIO_WHATSAPP_FALLBACK_TEMPLATE_SID or settings.TWILIO_WHATSAPP_TEMPLATE_SID
    # If free-form fails for any reason (including outside 24h customer-care),
    # try the approved template as a fallback so the user still gets a response.
    if fallback_sid:
        fallback_res = send_template_whatsapp(
            to=to,
            content_sid=fallback_sid,
            # Keep Content API variable structure stable even if we don't have
            # all values at this moment.
            content_variables={"1": "", "2": "", "3": ""},
        )
        if not getattr(fallback_res, "ok", False):
            logger.error(
                "Twilio fallback template send failed",
                to=to,
                content_sid=fallback_sid,
                error=getattr(fallback_res, "error", None),
            )
        if not getattr(fallback_res, "ok", False):
            logger.error(
                "Twilio fallback template send failed",
                to=to,
                body=body,
                error=getattr(fallback_res, "error", None),
            )


async def verify_twilio(request: Request, x_twilio_signature: str = Header(None)):
    if not settings.TWILIO_AUTH_TOKEN:
        return
    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    url = str(request.url)
    if request.headers.get("x-forwarded-proto") == "https":
        url = url.replace("http://", "https://")
    form_data = await request.form()
    post_vars = {k: str(v) for k, v in form_data.items()}
    if not validator.validate(url, post_vars, x_twilio_signature or ""):
        logger.warning(f"Invalid Twilio signature for URL: {url}")
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

@whatsapp_router.post("/whatsapp/inbound", include_in_schema=False, dependencies=[Depends(verify_twilio)])
async def twilio_whatsapp_inbound(request: Request, db: Session = Depends(get_mysql_db)):
    """
    Twilio WhatsApp webhook.
    Configure Twilio to POST incoming messages to:
      /api/v1/whatsapp/inbound
    """
    form = await request.form()
    from_raw = str(form.get("From", ""))
    body = str(form.get("Body", ""))
    message_sid = str(form.get("MessageSid", "") or "")

    phone = _normalize_from_twilio(from_raw)
    text = _clean_text(body)
    norm = _normalize_msg(text)

    if not phone:
        return PlainTextResponse("ok")

    # Idempotency: Twilio may retry the same inbound webhook.
    if message_sid and redis_conn:
        try:
            dedup_key = f"wa:inbound:{message_sid}"
            inserted = redis_conn.set(dedup_key, "1", ex=SESSION_TTL_SECONDS, nx=True)
            if inserted is None:
                logger.info(f"Skipping duplicate inbound message sid={message_sid}")
                return PlainTextResponse("ok")
        except Exception as e:
            logger.warning(f"Redis idempotency check failed: {e}")

    session = _get_session(phone)
    step = session.get("step") or "interest"

    logger.info(f"WhatsApp inbound from={phone} step={step} body={text!r}")

    # Always upsert a lead record early for tracking
    lead_id = _upsert_lead(db, phone, {"message": text})
    
    is_new_lead = False
    if not session:
        session = _default_session(lead_id)
        is_new_lead = True

    # Refresh session TTL on every inbound message so outbound replies
    # stay within the WhatsApp customer-care window.
    session["last_inbound_at"] = int(time.time())
    _set_session(phone, session)
    
    if is_new_lead:
        asyncio.create_task(_trigger_and_save_call(phone, lead_id, text or "Inbound WhatsApp lead"))

    # allow user to restart anytime
    if norm in {"hi", "hello", "start", "restart"}:
        session = _default_session(lead_id)
        _set_session(phone, session)
        _send_text_checked(to=phone, body=_ask_interest())
        return PlainTextResponse("ok")

    # STEP: interest
    if step == "interest":
        yn = _parse_yes_no(norm)
        if yn is None:
            _send_text_checked(to=phone, body=_ask_interest())
            session["step"] = "interest"
            _set_session(phone, session)
            return PlainTextResponse("ok")

        if yn is False:
            _update_lead_by_id(db, lead_id, {"status": "lost"})
            publish_event(lead_id, "WA_NOT_INTERESTED", "User not interested")
            _send_text_checked(
                to=phone,
                body="No worries — thanks! If you need options later, just reply HI.",
            )
            _clear_session(phone)
            return PlainTextResponse("ok")

        # Interested
        _update_lead_by_id(db, lead_id, {"status": "Connected / Interested (WhatsApp)"})
        publish_event(lead_id, "WA_INTERESTED", "User interested")
        session["data"]["interest"] = "yes"
        session["step"] = "property_type"
        _send_text_checked(to=phone, body=_ask_property_type())
        _set_session(phone, session)
        return PlainTextResponse("ok")

    # STEP: property_type
    if step == "property_type":
        ptype = _parse_property_type(norm)
        if not ptype:
            _send_text_checked(to=phone, body=_ask_property_type())
            return PlainTextResponse("ok")

        session["data"]["property_type"] = ptype
        _update_lead_by_id(db, lead_id, {"property_type": ptype, "status": "contacted"})
        publish_event(lead_id, "WA_PROPERTY_TYPE", f"Property type: {ptype}")
        session["step"] = "location"
        _set_session(phone, session)
        _send_text_checked(to=phone, body=_ask_location())
        return PlainTextResponse("ok")

    # STEP: location
    if step == "location":
        if len(text) < 2:
            _send_text_checked(to=phone, body=_ask_location())
            return PlainTextResponse("ok")

        session["data"]["location"] = text
        _update_lead_by_id(db, lead_id, {"location": text})
        publish_event(lead_id, "WA_LOCATION", f"Location: {text}")
        session["step"] = "move_in"
        _set_session(phone, session)
        _send_text_checked(to=phone, body=_ask_move_in())
        return PlainTextResponse("ok")

    # STEP: move_in
    if step == "move_in":
        mv = _parse_move_in(norm)
        if not mv:
            _send_text_checked(to=phone, body=_ask_move_in())
            return PlainTextResponse("ok")

        if mv == "immediate":
            session["data"]["move_in"] = "Immediate"
            session["data"]["move_in_date"] = ""

            lead_obj = lead_repo.get_lead_by_id(db, lead_id)
            merged = _merge_raw_payload(
                getattr(lead_obj, "raw_payload", None),
                {"whatsapp_flow": session["data"]},
            )
            _update_lead_by_id(db, lead_id, {"raw_payload": merged})
            publish_event(lead_id, "WA_MOVE_IN", "Immediate")
            rm = _assign_rm(db, lead_id)
            _send_text_checked(to=phone, body=_final_message_with_rm(rm))
            publish_event(lead_id, "WA_FLOW_COMPLETE", "Details collected; RM follow-up")
            _clear_session(phone)
            return PlainTextResponse("ok")

        # custom date
        session["data"]["move_in"] = "Custom"
        session["step"] = "date"
        _set_session(phone, session)
        _send_text_checked(to=phone, body=_ask_date())
        return PlainTextResponse("ok")

    # STEP: date
    if step == "date":
        d = _parse_date(text)
        if not d:
            _send_text_checked(to=phone, body=_ask_date())
            return PlainTextResponse("ok")

        session["data"]["move_in_date"] = d
        lead_obj = lead_repo.get_lead_by_id(db, lead_id)
        merged = _merge_raw_payload(
            getattr(lead_obj, "raw_payload", None),
            {"whatsapp_flow": session["data"]},
        )
        _update_lead_by_id(db, lead_id, {"raw_payload": merged})
        publish_event(lead_id, "WA_MOVE_IN_DATE", d)
        rm = _assign_rm(db, lead_id)
        _send_text_checked(to=phone, body=_final_message_with_rm(rm))
        publish_event(lead_id, "WA_FLOW_COMPLETE", "Details collected; RM follow-up")
        _clear_session(phone)
        return PlainTextResponse("ok")

    # Unknown state: reset
    _clear_session(phone)
    _send_text_checked(to=phone, body=_ask_interest())
    _set_session(phone, _default_session(lead_id))
    return PlainTextResponse("ok")


@whatsapp_router.post(
    "/leads/widget",
    tags=["WhatsApp"],
    summary="Capture a lead from the WhatsApp floating widget form",
    status_code=201,
)
async def submit_whatsapp_widget_lead(
    payload: WhatsAppWidgetLeadCreate,
    db: Session = Depends(get_mysql_db),
):
    """
    Public endpoint — no authentication required.

    Saves the details submitted via the website's WhatsApp floating widget
    (name, phone, email, preferred location, property type, message) as a
    new row in the `whatsapp_leads` table with source = "Website - WhatsApp Widget".
    """
    from app.repo import whatsapp_lead as whatsapp_lead_repo

    lead_data = {
        "name": payload.name,
        "phone": payload.phone,
        "email": payload.email or None,
        "preferred_location": payload.preferred_location or None,
        "property_type": payload.property_type or None,
        "message": payload.message or None,
        "source": payload.source,
    }

    try:
        new_lead = whatsapp_lead_repo.create_whatsapp_lead(db, lead_data)
        logger.info(
            f"WhatsApp widget lead captured: id={new_lead.id} "
            f"phone={payload.phone} source={payload.source!r}"
        )
        return WhatsAppWidgetLeadResponse(
            success=True,
            message="Lead captured successfully",
            lead_id=new_lead.id,
        )
    except Exception as e:
        logger.error(f"Failed to save WhatsApp widget lead for phone={payload.phone}: {e}")
        raise HTTPException(
            status_code=500,
            detail="We couldn't save your enquiry. Please try again."
        )


@whatsapp_router.post("/whatsapp/status", include_in_schema=False, dependencies=[Depends(verify_twilio)])
async def twilio_whatsapp_status(request: Request, db: Session = Depends(get_mysql_db)):
    """
    Twilio Status Callback for WhatsApp messages.
    Configure in Twilio console to POST message delivery updates here.
    """
    form = await request.form()

    message_sid = str(form.get("MessageSid", "") or "")
    message_status = str(form.get("MessageStatus", "") or "")

    # Twilio sends:
    # - To: whatsapp:+<E164>
    # - From: whatsapp:+<E164>
    to_raw = str(form.get("To", "") or "")
    from_raw = str(form.get("From", "") or "")

    error_code = form.get("ErrorCode")
    error_message = form.get("ErrorMessage")

    if not message_sid or not message_status:
        return PlainTextResponse("ok")

    # For outbound messages we care about the recipient (To).
    phone = _normalize_from_twilio(to_raw) or _normalize_from_twilio(from_raw)
    if not phone:
        return PlainTextResponse("ok")

    lead_obj = lead_repo.get_lead_by_phone_source(db, phone=phone, source=SOURCE)
    if not lead_obj:
        logger.info(
            "Twilio status for unknown lead",
            to=phone,
            message_sid=message_sid,
            status=message_status,
        )
        return PlainTextResponse("ok")

    status_upper = message_status.upper()
    # Twilio status values: sent, delivered, read, failed (case-insensitive)
    if status_upper in {"SENT", "DELIVERED", "READ"}:
        event_type = f"WA_{status_upper}"
    elif status_upper == "FAILED":
        event_type = "WA_FAILED"
    else:
        event_type = f"WA_STATUS_{status_upper}"

    payload = {
        "message_sid": message_sid,
        "status": message_status,
        "to": to_raw,
        "from": from_raw,
        "error_code": error_code,
        "error_message": error_message,
    }
    publish_event(
        lead_obj.id,
        event_type,
        message=f"Twilio message status: {message_status}",
        payload=payload,
    )
    return PlainTextResponse("ok")

