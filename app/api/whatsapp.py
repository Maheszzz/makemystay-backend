from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core.redis import redis_conn
from app.events.event_service import publish_event
from app.models.agent import Agent
from app.models.lead import Lead
from app.repo import agent_repo
from app.repo import lead as lead_repo
from app.services.assignment_service import assign_lead
from app.services.whatsapp_service import send_text_whatsapp


whatsapp_router = APIRouter(tags=["WhatsApp"])


SESSION_TTL_SECONDS = 60 * 60 * 48  # 48 hours
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
    val = redis_conn.get(_sess_key(phone))
    if not val:
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}


def _set_session(phone: str, data: Dict[str, Any]) -> None:
    if not redis_conn:
        return
    redis_conn.setex(_sess_key(phone), SESSION_TTL_SECONDS, json.dumps(data))


def _clear_session(phone: str) -> None:
    if not redis_conn:
        return
    redis_conn.delete(_sess_key(phone))


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _normalize_msg(msg: str) -> str:
    """
    Light normalization so users can type text instead of only 1/2/3.
    """
    b = _clean_text(msg).lower()
    b = b.replace("one bhk", "1bhk").replace("two bhk", "2bhk").replace("three bhk", "3bhk")
    if "1bhk" in b or "1 bhk" in b:
        return "2"
    if "2bhk" in b or "2 bhk" in b:
        return "3"
    if "3bhk" in b or "3 bhk" in b:
        return "4"
    if "pg" in b:
        return "1"
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


def _ask_interest(name: str | None = None) -> str:
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
        "data": {
            "interest": "",
            "property_type": "",
            "location": "",
            "move_in": "",
            "move_in_date": "",
        },
    }


@whatsapp_router.post("/whatsapp/inbound", include_in_schema=False)
async def twilio_whatsapp_inbound(request: Request, db: Session = Depends(get_mysql_db)):
    """
    Twilio WhatsApp webhook.
    Configure Twilio to POST incoming messages to:
      /api/v1/whatsapp/inbound
    """
    form = await request.form()
    from_raw = str(form.get("From", ""))
    body = str(form.get("Body", ""))

    phone = _normalize_from_twilio(from_raw)
    text = _clean_text(body)
    norm = _normalize_msg(text)

    if not phone:
        return PlainTextResponse("ok")

    session = _get_session(phone)
    step = session.get("step") or "interest"

    logger.info(f"WhatsApp inbound from={phone} step={step} body={text!r}")

    # Always upsert a lead record early for tracking
    lead_id = _upsert_lead(db, phone, {"message": text})
    if not session:
        session = _default_session(lead_id)
        _set_session(phone, session)

    # allow user to restart anytime
    if norm in {"hi", "hello", "start", "restart"}:
        session = _default_session(lead_id)
        _set_session(phone, session)
        send_text_whatsapp(to=phone, body=_ask_interest())
        return PlainTextResponse("ok")

    # STEP: interest
    if step == "interest":
        yn = _parse_yes_no(norm)
        if yn is None:
            send_text_whatsapp(to=phone, body=_ask_interest())
            session["step"] = "interest"
            _set_session(phone, session)
            return PlainTextResponse("ok")

        if yn is False:
            _update_lead_by_id(db, lead_id, {"status": "lost"})
            publish_event(lead_id, "WA_NOT_INTERESTED", "User not interested")
            send_text_whatsapp(to=phone, body="No worries — thanks! If you need options later, just reply HI.")
            _clear_session(phone)
            return PlainTextResponse("ok")

        # Interested
        publish_event(lead_id, "WA_INTERESTED", "User interested")
        session["data"]["interest"] = "yes"
        session["step"] = "property_type"
        send_text_whatsapp(to=phone, body=_ask_property_type())
        _set_session(phone, session)
        return PlainTextResponse("ok")

    # STEP: property_type
    if step == "property_type":
        ptype = _parse_property_type(norm)
        if not ptype:
            send_text_whatsapp(to=phone, body=_ask_property_type())
            return PlainTextResponse("ok")

        session["data"]["property_type"] = ptype
        _update_lead_by_id(db, lead_id, {"property_type": ptype, "status": "contacted"})
        publish_event(lead_id, "WA_PROPERTY_TYPE", f"Property type: {ptype}")
        session["step"] = "location"
        _set_session(phone, session)
        send_text_whatsapp(to=phone, body=_ask_location())
        return PlainTextResponse("ok")

    # STEP: location
    if step == "location":
        if len(text) < 2:
            send_text_whatsapp(to=phone, body=_ask_location())
            return PlainTextResponse("ok")

        session["data"]["location"] = text
        _update_lead_by_id(db, lead_id, {"location": text})
        publish_event(lead_id, "WA_LOCATION", f"Location: {text}")
        session["step"] = "move_in"
        _set_session(phone, session)
        send_text_whatsapp(to=phone, body=_ask_move_in())
        return PlainTextResponse("ok")

    # STEP: move_in
    if step == "move_in":
        mv = _parse_move_in(norm)
        if not mv:
            send_text_whatsapp(to=phone, body=_ask_move_in())
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
            send_text_whatsapp(to=phone, body=_final_message_with_rm(rm))
            publish_event(lead_id, "WA_FLOW_COMPLETE", "Details collected; RM follow-up")
            _clear_session(phone)
            return PlainTextResponse("ok")

        # custom date
        session["data"]["move_in"] = "Custom"
        session["step"] = "date"
        _set_session(phone, session)
        send_text_whatsapp(to=phone, body=_ask_date())
        return PlainTextResponse("ok")

    # STEP: date
    if step == "date":
        d = _parse_date(text)
        if not d:
            send_text_whatsapp(to=phone, body=_ask_date())
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
        send_text_whatsapp(to=phone, body=_final_message_with_rm(rm))
        publish_event(lead_id, "WA_FLOW_COMPLETE", "Details collected; RM follow-up")
        _clear_session(phone)
        return PlainTextResponse("ok")

    # Unknown state: reset
    _clear_session(phone)
    send_text_whatsapp(to=phone, body=_ask_interest())
    _set_session(phone, _default_session(lead_id))
    return PlainTextResponse("ok")

