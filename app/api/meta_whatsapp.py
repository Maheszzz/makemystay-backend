from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from loguru import logger
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core.config import settings
from app.core.redis import redis_conn
from app.events.event_service import publish_event
from app.models.agent import Agent
from app.models.lead import Lead
from app.repo import agent_repo
from app.repo import lead as lead_repo
from app.services.assignment_service import assign_lead

meta_whatsapp_router = APIRouter(tags=["Meta WhatsApp"])

SOURCE = "meta_whatsapp"
SESSION_TTL_SECONDS = 60 * 60 * 24  # 24h

PROPERTY_TYPE_CHOICES = {"PG": "PG", "1BHK": "1BHK", "2BHK": "2BHK"}
LOCATION_CHOICES = {
    "BTM": "BTM Layout",
    "HSR": "HSR Layout",
    "WHITEFIELD": "Whitefield",
}
MOVE_IN_CHOICES = {"NOW": "Immediate", "DATE": "Custom"}


def _sess_key(phone: str) -> str:
    return f"wa:meta:flow:{phone}"


def _get_session(phone: str) -> Dict[str, Any]:
    if not redis_conn:
        return {}
    raw = redis_conn.get(_sess_key(phone))
    if not raw:
        return {}
    try:
        return json.loads(raw)
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


def _assign_rm(db: Session, lead_id: int) -> Optional[Agent]:
    """
    Same RM assignment approach as the Twilio WhatsApp flow:
    - Lock available agents for update
    - Choose based on conversion/load
    - Increase current_load and set lead.assigned_to
    """
    lead_obj: Optional[Lead] = lead_repo.get_lead_by_id(db, lead_id)
    if not lead_obj:
        return None

    try:
        agents = agent_repo.get_available_agents_for_update(
            db, location=lead_obj.location
        )
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


def _final_message_with_rm(rm: Optional[Agent]) -> str:
    if not rm:
        return "Perfect — thanks! Our RM will contact you shortly.\nHave a great day!"
    return (
        "Perfect — thanks! Our RM will contact you shortly.\n"
        f"{rm.name}\n"
        f"📞 {rm.phone}\n\n"
        "Have a great day!"
    )


async def _meta_post_message(payload: Dict[str, Any]) -> None:
    """
    Send an outbound WhatsApp message via Meta Graph API.
    Raises HTTPException on failure.
    """
    if not settings.WHATSAPP_TOKEN or not settings.PHONE_NUMBER_ID:
        raise HTTPException(status_code=500, detail="Meta WhatsApp not configured")

    url = (
        f"https://graph.facebook.com/{settings.META_GRAPH_API_VERSION}/"
        f"{settings.PHONE_NUMBER_ID}/messages"
    )
    headers = {"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Meta WhatsApp send failed: {resp.status_code} {resp.text}",
            )


async def send_property_type_buttons(to: str) -> None:
    await _meta_post_message(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "Hi 👋 What are you looking for?"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "PG", "title": "PG"}},
                        {"type": "reply", "reply": {"id": "1BHK", "title": "1 BHK"}},
                        {"type": "reply", "reply": {"id": "2BHK", "title": "2 BHK"}},
                    ]
                },
            },
        }
    )


async def send_location_list(to: str) -> None:
    await _meta_post_message(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": "Select your preferred location"},
                "action": {
                    "button": "Choose location",
                    "sections": [
                        {
                            "title": "Available Areas",
                            "rows": [
                                {"id": "BTM", "title": "BTM Layout"},
                                {"id": "HSR", "title": "HSR Layout"},
                                {"id": "WHITEFIELD", "title": "Whitefield"},
                            ],
                        }
                    ],
                },
            },
        }
    )


async def send_move_in_buttons(to: str) -> None:
    await _meta_post_message(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": "When are you planning to move in?"},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": "NOW", "title": "Immediate"}},
                        {"type": "reply", "reply": {"id": "DATE", "title": "Select Date"}},
                    ]
                },
            },
        }
    )


async def send_move_in_date_prompt(to: str) -> None:
    await _meta_post_message(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {
                "body": "Please reply with your move-in date in this format: YYYY-MM-DD"
            },
        }
    )


async def send_final(to: str, rm: Optional[Agent]) -> None:
    await _meta_post_message(
        {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": _final_message_with_rm(rm)},
        }
    )


def _normalize_free_text(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _parse_date(text: str) -> Optional[str]:
    try:
        dt = datetime.strptime(text.strip(), "%Y-%m-%d")
        return dt.date().isoformat()
    except Exception:
        return None


def _default_session(lead_id: int) -> Dict[str, Any]:
    return {
        "step": "property_type",
        "lead_id": lead_id,
        "data": {
            "property_type": "",
            "location": "",
            "move_in": "",
            "move_in_date": "",
        },
    }


async def handle_message(db: Session, msg: Dict[str, Any]) -> None:
    phone = msg.get("from")
    if not phone:
        return

    message_id = msg.get("id")
    if message_id and redis_conn:
        dedup_key = f"wa:meta:inbound:{message_id}"
        inserted = redis_conn.set(dedup_key, "1", ex=SESSION_TTL_SECONDS, nx=True)
        if inserted is None:
            logger.info(f"Skipping duplicate inbound meta message_id={message_id}")
            return

    # Upsert lead early so we have an audit trail even if sending fails.
    lead_id = _upsert_lead(db, phone, {"message": json.dumps(msg)[:1000]})

    session = _get_session(phone)
    if not session:
        session = _default_session(lead_id)
        _set_session(phone, session)

    # Always treat inbound as "fresh" within our local session TTL.
    session["last_inbound_at"] = int(datetime.utcnow().timestamp())
    _set_session(phone, session)

    msg_type = msg.get("type")

    # Allow restart any time using a simple keyword
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "") or ""
        nt = _normalize_free_text(text)
        if nt in {"hi", "hello", "start", "restart"} or "property" in nt:
            session = _default_session(lead_id)
            _set_session(phone, session)
            await send_property_type_buttons(phone)
            return

    if msg_type == "interactive":
        interactive = msg.get("interactive", {})
        itype = interactive.get("type")

        if itype == "button_reply":
            choice = interactive.get("button_reply", {}).get("id")
        elif itype == "list_reply":
            choice = interactive.get("list_reply", {}).get("id")
        else:
            choice = None

        step = session.get("step") or "property_type"

        if choice in PROPERTY_TYPE_CHOICES and step in {"property_type", "location"}:
            ptype = PROPERTY_TYPE_CHOICES[choice]
            session["data"]["property_type"] = ptype
            session["step"] = "location"
            _set_session(phone, session)
            lead_obj = lead_repo.get_lead_by_id(db, lead_id)
            if lead_obj:
                lead_repo.update_lead(db, lead_obj, {"property_type": ptype})
            publish_event(lead_id, "META_PROPERTY_TYPE", f"Property type: {ptype}")
            await send_location_list(phone)
            return

        if choice in LOCATION_CHOICES and step in {"location", "move_in"}:
            loc = LOCATION_CHOICES[choice]
            session["data"]["location"] = loc
            session["step"] = "move_in"
            _set_session(phone, session)
            lead_obj = lead_repo.get_lead_by_id(db, lead_id)
            if lead_obj:
                lead_repo.update_lead(db, lead_obj, {"location": loc})
            publish_event(lead_id, "META_LOCATION", f"Location: {loc}")
            await send_move_in_buttons(phone)
            return

        if choice in MOVE_IN_CHOICES and step == "move_in":
            mv = MOVE_IN_CHOICES[choice]
            session["data"]["move_in"] = mv
            if mv == "Immediate":
                session["step"] = "completed"
            else:
                session["step"] = "move_in_date"
            _set_session(phone, session)

            payload = {
                "meta_flow": session["data"],
                "status": "completed" if mv == "Immediate" else "pending",
            }
            lead_obj = lead_repo.get_lead_by_id(db, lead_id)
            lead_updates: Dict[str, Any] = {"raw_payload": payload}

            publish_event(lead_id, "META_MOVE_IN", f"Move-in: {mv}")

            if mv == "Immediate":
                lead_updates["status"] = "converted"
                if lead_obj:
                    lead_repo.update_lead(db, lead_obj, lead_updates)
                rm = _assign_rm(db, lead_id)
                await send_final(phone, rm)
                _clear_session(phone)
            else:
                if lead_obj:
                    lead_repo.update_lead(db, lead_obj, lead_updates)
                await send_move_in_date_prompt(phone)
            return

        # If we got a button/list reply in a mismatched step, just fall through.
        await send_property_type_buttons(phone)
        session = _default_session(lead_id)
        _set_session(phone, session)
        return

    # Handle date text when waiting for it
    if msg_type == "text" and session.get("step") == "move_in_date":
        text = msg.get("text", {}).get("body", "") or ""
        d = _parse_date(text)
        if not d:
            await send_move_in_date_prompt(phone)
            return

        session["data"]["move_in_date"] = d
        session["step"] = "completed"
        _set_session(phone, session)

        payload = {"meta_flow": session["data"], "status": "completed"}
        lead_obj = lead_repo.get_lead_by_id(db, lead_id)
        if lead_obj:
            lead_repo.update_lead(
                db,
                lead_obj,
                {"raw_payload": payload, "status": "converted"},
            )

        publish_event(lead_id, "META_MOVE_IN_DATE", f"Move-in date: {d}")
        rm = _assign_rm(db, lead_id)
        await send_final(phone, rm)
        _clear_session(phone)
        return


@meta_whatsapp_router.get("/meta/whatsapp/webhook", include_in_schema=False)
async def verify_meta_webhook(request: Request):
    """
    Meta webhook verification endpoint.
    Configure in Meta: hub.verify_token should match VERIFY_TOKEN.
    """
    q = request.query_params
    mode = q.get("hub.mode")
    verify_token = q.get("hub.verify_token")
    challenge = q.get("hub.challenge")

    if mode == "subscribe" and verify_token == settings.VERIFY_TOKEN:
        if challenge:
            return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Invalid verification token")


@meta_whatsapp_router.post("/meta/whatsapp/webhook", include_in_schema=False)
async def meta_whatsapp_webhook(request: Request, db: Session = Depends(get_mysql_db)):
    """
    Meta WhatsApp Cloud webhook (interactive button replies + list replies).
    """
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    entries = data.get("entry", []) or []
    for entry in entries:
        changes = entry.get("changes", []) or []
        for change in changes:
            value = change.get("value", {}) or {}
            messages = value.get("messages", []) or []
            for msg in messages:
                try:
                    await handle_message(db, msg)
                except HTTPException as e:
                    logger.error(f"Meta handle_message HTTP error: {e.detail}")
                except Exception as e:
                    logger.error(f"Meta handle_message failed: {e}")

    return PlainTextResponse("ok")

