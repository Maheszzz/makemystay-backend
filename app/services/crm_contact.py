"""Push a saved website contact into the Realty CRM as a lead."""

from typing import Any, Dict

import httpx
from loguru import logger

from app.core.config import settings


def push_contact_to_crm(contact: Dict[str, Any], contact_id: int) -> None:
    url = (settings.CRM_WEBHOOK_URL or "").strip()
    secret = (settings.CRM_WEBHOOK_SECRET or "").strip()
    if not url or not secret:
        logger.info("CRM webhook not configured; skipping contact #{}", contact_id)
        return

    payload = {
        "name": contact.get("name_") or contact.get("name") or "",
        "phone": contact.get("phone"),
        "email": contact.get("email"),
        "message": contact.get("message") or "",
        "location": contact.get("location"),
        "property_type": contact.get("property_type"),
        "source": contact.get("source") or "Website",
    }
    try:
        response = httpx.post(
            url,
            json=payload,
            headers={"X-API-Key": secret},
            timeout=10.0,
        )
        response.raise_for_status()
        logger.info("Contact #{} pushed to CRM ({})", contact_id, response.status_code)
    except Exception as exc:
        logger.error("Failed to push contact #{} to CRM: {}", contact_id, exc)
