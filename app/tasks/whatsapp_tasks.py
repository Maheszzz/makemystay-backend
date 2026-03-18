"""RQ tasks for Twilio WhatsApp bulk sending.

Runs outside the request cycle. Each task logs per-lead events for auditability.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.config import settings
from app.events.event_service import publish_event
from app.services.whatsapp_service import send_template_whatsapp


def send_whatsapp_bulk_task(
    *,
    leads: List[Dict[str, Any]],
    content_sid: str,
    per_message_delay_ms: int = 500,
) -> Dict[str, Any]:
    """
    leads: list of dicts like:
      { phone, lead_id?, variables? or name/city/budget }
    """
    if not content_sid:
        raise ValueError("content_sid is required")

    delay_s = max(0, per_message_delay_ms) / 1000.0
    results = {"sent": 0, "failed": 0, "total": len(leads), "errors": []}

    logger.info(f"WhatsApp bulk send started: total={len(leads)} delay_ms={per_message_delay_ms}")

    for i, lead in enumerate(leads):
        phone = (lead.get("phone") or "").strip()
        lead_id: Optional[int] = lead.get("lead_id")

        variables = lead.get("variables")
        if not isinstance(variables, dict):
            # Default variable mapping: "1": name, "2": city, "3": budget
            variables = {
                "1": (lead.get("name") or ""),
                "2": (lead.get("city") or ""),
                "3": (lead.get("budget") or ""),
            }

        if not phone:
            results["failed"] += 1
            results["errors"].append({"index": i, "error": "missing_phone"})
            continue

        r = send_template_whatsapp(
            to=phone,
            from_=settings.TWILIO_WHATSAPP_FROM,
            content_sid=content_sid,
            content_variables=variables,
        )

        if r.ok:
            results["sent"] += 1
            if lead_id:
                publish_event(
                    lead_id,
                    "WHATSAPP_SENT",
                    "WhatsApp template message sent",
                    payload={"sid": r.sid, "to": phone},
                )
        else:
            results["failed"] += 1
            results["errors"].append({"index": i, "to": phone, "error": r.error})
            if lead_id:
                publish_event(
                    lead_id,
                    "WHATSAPP_FAILED",
                    "WhatsApp template message failed",
                    payload={"to": phone, "error": r.error},
                )

        if delay_s:
            time.sleep(delay_s)

    logger.info(f"WhatsApp bulk send finished: sent={results['sent']} failed={results['failed']}")
    return results

