"""Retell AI API endpoints for creating web calls and outbound phone calls."""

import httpx
from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from app.core.config import settings

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
        "retell_llm_dynamic_variables": {
            "name": name,
            "location": location,
            "property_type": property_type,
            "requirement": message or "interested in property options",
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

    except httpx.RequestError as e:
        logger.error(f"Network error triggering call: {str(e)}")

    except Exception as e:
        logger.error(f"Unexpected error triggering call: {str(e)}")

# -----------------------------------------
# Retell Webhook (Status / Call Events)
# -----------------------------------------
@retell_router.post("/retell/webhook")
async def retell_webhook(request: Request):
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

        # You can add logic here to update lead status or log call details
        # based on 'call_ended', 'call_started', etc.

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Error processing Retell webhook: {str(e)}")
        # Return 200 anyway to avoid Retell retries if the error is on our side or payload format
        return {"status": "error", "message": str(e)}
