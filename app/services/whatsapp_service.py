from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger

from app.core.config import settings


@dataclass(frozen=True)
class WhatsAppSendResult:
    ok: bool
    sid: Optional[str] = None
    error: Optional[str] = None


def _normalize_to_whatsapp(to: str) -> str:
    """
    Twilio expects `to` and `from_` formatted like: "whatsapp:+<E164>".
    We accept "+<E164>" or "whatsapp:+<E164>" and normalize to the latter.
    """
    raw = (to or "").strip()
    if raw.startswith("whatsapp:"):
        return raw
    if raw.startswith("+"):
        return f"whatsapp:{raw}"
    # If caller passes plain digits, we still prefix whatsapp: but leave number unchanged.
    # Prefer passing E.164 (+91...) from the caller.
    return f"whatsapp:{raw}"


def send_template_whatsapp(
    *,
    to: str,
    content_sid: str,
    content_variables: Dict[str, Any],
    from_: Optional[str] = None,
) -> WhatsAppSendResult:
    """
    Send a WhatsApp message using Twilio Content API (approved template).
    """
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return WhatsAppSendResult(ok=False, error="Twilio credentials not configured")

    from_value = (from_ or settings.TWILIO_WHATSAPP_FROM or "").strip()
    if not from_value:
        return WhatsAppSendResult(ok=False, error="TWILIO_WHATSAPP_FROM not configured")

    if not content_sid:
        return WhatsAppSendResult(ok=False, error="content_sid is required")

    try:
        from twilio.rest import Client  # type: ignore[import-not-found]  # imported lazily

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=from_value,
            to=_normalize_to_whatsapp(to),
            content_sid=content_sid,
            content_variables=content_variables,
        )
        return WhatsAppSendResult(ok=True, sid=msg.sid)
    except Exception as e:
        logger.error(f"Twilio WhatsApp send failed: {e}")
        return WhatsAppSendResult(ok=False, error=str(e))


def send_text_whatsapp(*, to: str, body: str, from_: Optional[str] = None) -> WhatsAppSendResult:
    """Send a free-form WhatsApp message (requires 24h customer care window)."""
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return WhatsAppSendResult(ok=False, error="Twilio credentials not configured")

    from_value = (from_ or settings.TWILIO_WHATSAPP_FROM or "").strip()
    if not from_value:
        return WhatsAppSendResult(ok=False, error="TWILIO_WHATSAPP_FROM not configured")

    if not body:
        return WhatsAppSendResult(ok=False, error="body is required")

    try:
        from twilio.rest import Client  # type: ignore[import-not-found]

        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=from_value,
            to=_normalize_to_whatsapp(to),
            body=body,
        )
        return WhatsAppSendResult(ok=True, sid=msg.sid)
    except Exception as e:
        logger.error(f"Twilio WhatsApp text send failed: {e}")
        return WhatsAppSendResult(ok=False, error=str(e))

