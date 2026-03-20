import base64
import hashlib
import hmac
import os
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional

import jinja2
import qrcode
import razorpay
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.configs.db_config import get_db
from app.core.config import settings
from app.models.payment import Payment
from app.models.payment_webhook_event import PaymentWebhookEvent
from app.services.payment_normalization import _map_status, normalize_transaction
from app.schemas.payment import (
    PaymentSchema,
    PaymentTransactionSchema,
    ServiceFeeValidationRequest,
    ValidationResponse,
)

router = APIRouter()

# Initialize Razorpay client
RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET = settings.RAZORPAY_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET = settings.RAZORPAY_WEBHOOK_SECRET

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


class CreateOrderRequest(BaseModel):
    amount: int  # in paise
    currency: str = "INR"
    payment_type: str = "booking"
    payer_name: Optional[str] = None
    payer_email: Optional[str] = None
    payer_phone: Optional[str] = None


def _map_webhook_event_to_status(event_name: Optional[str]) -> Optional[str]:
    if not event_name:
        return None
    event = str(event_name).strip().lower()
    if event in {"payment.captured", "order.paid", "payment_link.paid"}:
        return "captured"
    if event in {"payment.failed", "payment_link.expired", "payment_link.cancelled"}:
        return "failed"
    return None


def _extract_payment_entity_from_webhook_payload(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    payload_root = payload.get("payload", {})
    if not isinstance(payload_root, dict):
        return {}
    payment_obj = payload_root.get("payment", {})
    if not isinstance(payment_obj, dict):
        return {}
    entity = payment_obj.get("entity", {})
    return entity if isinstance(entity, dict) else {}


def _fetch_razorpay_payment(payment_id: str) -> Optional[Dict[str, Any]]:
    if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        return None

    try:
        with httpx.Client(timeout=8.0, auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) as http:
            response = http.get(f"https://api.razorpay.com/v1/payments/{payment_id}")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.warning(f"Unable to fetch Razorpay payment {payment_id}: {e}")
        return None


def _fetch_order_payment(order_id: str) -> Optional[Dict[str, Any]]:
    if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
        return None

    try:
        with httpx.Client(timeout=8.0, auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) as http:
            response = http.get(f"https://api.razorpay.com/v1/orders/{order_id}/payments")
            response.raise_for_status()
            data = response.json()
            items = data.get("items") or []
            if not items:
                return None

            # Prefer the most meaningful transaction first.
            priorities = {"captured": 3, "authorized": 2, "created": 1}
            items_sorted = sorted(
                items,
                key=lambda p: priorities.get(str(p.get("status", "")).lower(), 0),
                reverse=True,
            )
            return items_sorted[0]
    except Exception as e:
        logger.warning(f"Unable to fetch Razorpay order payments for {order_id}: {e}")
        return None


@router.post("/payments/validate-fee", response_model=ValidationResponse)
def validate_service_fee(data: ServiceFeeValidationRequest):
    logger.info(
        f"Validating fee for property {data.property_id} ({data.property_type})"
    )

    prop_type = data.property_type.upper()
    fee = data.service_fee_amount
    fee_type = data.service_fee_type

    is_valid = False
    message = "Invalid service fee configuration"

    if prop_type in ["PG", "COLIVE PG"]:
        if fee_type == "sharing" and fee == 1500:
            is_valid = True
            message = "Valid Sharing PG Fee"
        elif fee_type == "private" and fee == 2500:
            is_valid = True
            message = "Valid Private PG Fee"
        else:
            message = "Invalid fee for PG. Expected 1500 (Sharing) or 2500 (Private)."

    elif prop_type == "1BHK":
        if fee == 4000:
            is_valid = True
            message = "Valid 1BHK Fee"
        else:
            message = "Invalid fee for 1BHK. Expected 4000."

    elif prop_type == "2BHK":
        if fee == 6000:
            is_valid = True
            message = "Valid 2BHK Fee"
        else:
            message = "Invalid fee for 2BHK. Expected 6000."

    else:
        # Fallback or other types validation
        if fee > 0:
            is_valid = True
            message = "Fee accepted for other property types"

    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    return {"valid": is_valid, "message": message}


@router.post("/payments/create-order")
def create_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    data_dict = {
        "amount": data.amount,
        "currency": data.currency,
        "payment_capture": 1,
    }

    try:
        # Use explicit timeouts so the API never leaves the frontend waiting forever.
        with httpx.Client(timeout=10.0, auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) as http:
            resp = http.post(
                "https://api.razorpay.com/v1/orders",
                json=data_dict,
            )
            resp.raise_for_status()
            order = resp.json()

        # Save to DB
        db_payment = Payment(
            amount=data.amount / 100,  # Store in rupees
            currency=data.currency,
            payment_type=data.payment_type,
            status="pending",
            order_id=order["id"],
            payer_name=data.payer_name,
            payer_email=data.payer_email,
            payer_phone=data.payer_phone,
        )
        db.add(db_payment)
        db.commit()
        db.refresh(db_payment)

        return order
    except httpx.TimeoutException:
        logger.error("Razorpay order create timed out")
        raise HTTPException(status_code=503, detail="Razorpay request timed out")
    except httpx.ProxyError as e:
        # Common when server is behind a restrictive corporate proxy / no outbound internet.
        logger.error(f"Razorpay order create proxy error: {e!r}")
        raise HTTPException(
            status_code=503,
            detail="Razorpay is unreachable from the server (proxy/internet blocked).",
        )
    except httpx.RequestError as e:
        # Any other network-level issues (DNS, connection resets, etc.)
        logger.error(f"Razorpay order create request error: {e!r}")
        raise HTTPException(
            status_code=503,
            detail="Razorpay request failed due to network connectivity from the server.",
        )
    except httpx.HTTPStatusError as e:
        # Razorpay usually returns JSON with error details.
        text = getattr(e.response, "text", "") or str(e)
        logger.error(f"Razorpay order create failed: {text}")
        raise HTTPException(status_code=503, detail="Razorpay order create failed")
    except Exception as e:
        logger.error(f"Error creating Razorpay order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payments/verify")
async def verify_payment(req: Request, db: Session = Depends(get_db)):
    body = await req.json()

    razorpay_order_id = body.get("razorpay_order_id")
    razorpay_payment_id = body.get("razorpay_payment_id")
    razorpay_signature = body.get("razorpay_signature")

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        raise HTTPException(status_code=400, detail="Missing payment details")

    try:
        # Verify signature
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )

        # Update DB
        payment = (
            db.query(Payment).filter(Payment.order_id == razorpay_order_id).first()
        )
        if payment:
            payment.status = "success"
            payment.payment_id = razorpay_payment_id
            payment.signature = razorpay_signature
            db.commit()

        return {"status": "success", "payment_id": razorpay_payment_id}
    except razorpay.errors.SignatureVerificationError:
        # Update DB to failed if possible
        payment = (
            db.query(Payment).filter(Payment.order_id == razorpay_order_id).first()
        )
        if payment:
            payment.status = "failed"
            payment.payment_id = razorpay_payment_id
            payment.signature = razorpay_signature
            db.commit()

        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/payments/webhook")
async def razorpay_webhook(req: Request, db: Session = Depends(get_db)):
    """Handle Razorpay server-to-server webhook events."""
    raw_body = await req.body()
    raw_body_text = raw_body.decode("utf-8", errors="replace")
    received_signature = req.headers.get("X-Razorpay-Signature", "")

    def log_webhook_event(
        *,
        event: str = "",
        status: str,
        reason: Optional[str] = None,
        order_id: Optional[str] = None,
        payment_id: Optional[str] = None,
        signature_valid: bool = False,
        payload: Optional[dict] = None,
    ) -> None:
        try:
            db.add(
                PaymentWebhookEvent(
                    provider="razorpay",
                    event=event or None,
                    status=status,
                    reason=reason,
                    order_id=order_id,
                    payment_id=payment_id,
                    signature_valid=signature_valid,
                    signature_header=received_signature or None,
                    payload=payload,
                    raw_body=raw_body_text[:10000],
                )
            )
            db.commit()
        except Exception as log_error:
            db.rollback()
            logger.error(f"Failed to persist webhook audit event: {log_error}")

    if not RAZORPAY_WEBHOOK_SECRET:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured")
        log_webhook_event(status="error", reason="webhook_secret_not_configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    if not received_signature:
        log_webhook_event(status="rejected", reason="missing_signature")
        raise HTTPException(status_code=400, detail="Missing webhook signature")

    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, received_signature):
        logger.warning("Invalid Razorpay webhook signature")
        log_webhook_event(status="rejected", reason="invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    try:
        payload = await req.json()
    except Exception:
        log_webhook_event(
            status="rejected", reason="invalid_json", signature_valid=True
        )
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", "")
    payload_data = payload.get("payload", {})
    payment_entity = payload_data.get("payment", {}).get("entity", {})
    payment_link_entity = payload_data.get("payment_link", {}).get("entity", {})

    order_id = payment_entity.get("order_id") or payment_link_entity.get("order_id")
    payment_id = payment_entity.get("id") or payment_link_entity.get("payment_id")

    payment = None
    if order_id:
        payment = db.query(Payment).filter(Payment.order_id == order_id).first()
    elif payment_id:
        payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
    else:
        # Acknowledge unknown payload formats to avoid repeated retries.
        logger.warning(
            f"Razorpay webhook missing identifiers for event={event}; payload keys={list(payload_data.keys())}"
        )
        log_webhook_event(
            event=event,
            status="ignored",
            reason="identifiers_missing",
            signature_valid=True,
            payload=payload,
        )
        return {"status": "ignored", "reason": "identifiers_missing"}

    if not payment:
        logger.warning(
            f"Payment not found for Razorpay webhook event={event}, order_id={order_id}, payment_id={payment_id}"
        )
        log_webhook_event(
            event=event,
            status="ignored",
            reason="payment_not_found",
            order_id=order_id,
            payment_id=payment_id,
            signature_valid=True,
            payload=payload,
        )
        return {"status": "ignored", "reason": "payment_not_found"}

    success_events = {"payment.captured", "order.paid", "payment_link.paid"}
    failed_events  = {"payment.failed", "payment_link.expired", "payment_link.cancelled"}
    # authorized = money reserved but NOT yet captured; keep as pending so the
    # admin dashboard doesn't wrongly show it as success.
    pending_events = {"payment.authorized"}

    if event in success_events:
        payment.status = "success"

        # -------------------------------------------------------------------
        # BUSINESS LOGIC: PAYMENT -> BOOKING MAPPING (PG SYSTEM)
        # When a payment is successfully captured via webhook, update booking.
        #
        # booking = db.query(Booking).filter(Booking.order_id == payment.order_id).first()
        # if booking:
        #     booking.payment_status = "PAID"
        #     booking.user_id = payment.user_id
        # -------------------------------------------------------------------

    elif event in pending_events:
        # Keep DB status as pending; just record the payment_id so the row
        # can be linked once capture fires.
        pass

    elif event in failed_events:
        payment.status = "failed"

    else:
        log_webhook_event(
            event=event,
            status="ignored",
            reason="event_not_mapped",
            order_id=order_id,
            payment_id=payment_id,
            signature_valid=True,
            payload=payload,
        )
        return {"status": "ignored", "reason": "event_not_mapped", "event": event}

    if payment_id:
        payment.payment_id = payment_id

    db.commit()
    log_webhook_event(
        event=event,
        status="processed",
        reason="payment_updated",
        order_id=order_id,
        payment_id=payment_id,
        signature_valid=True,
        payload=payload,
    )
    return {"status": "ok"}


def create_receipt_pdf(payment: Payment):
    os.makedirs("receipts", exist_ok=True)
    file_path = f"receipts/{payment.payment_id}.pdf"

    try:
        from weasyprint import HTML
    except ImportError as e:
        logger.error(
            f"WeasyPrint is not currently installed or configured properly (requires Pango/Cairo): {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="PDF generation currently unavailable due to missing system dependencies.",
        )

    try:
        date_str = (
            payment.created_at.strftime("%d %b %Y")
            if payment.created_at is not None
            else datetime.now().strftime("%d %b %Y")
        )
    except Exception:
        date_str = datetime.now().strftime("%d %b %Y")

    receipt_id = (
        f"MMS-{datetime.now().year}-{payment.id:04d}"
        if getattr(payment, "id", None)
        else f"MMS-{datetime.now().year}-0000"
    )

    # Generate QR Code
    qr_data = f"https://makemystay.com/receipt/{payment.payment_id}"
    qr = qrcode.make(qr_data)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # Load Logo
    logo_base64 = None
    logo_path = os.path.join(os.path.dirname(__file__), "../templates/logo.svg")
    try:
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as image_file:
                logo_base64 = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to load or encode logo.svg: {e}")

    # Load Jinja2 Template
    try:
        template_loader = jinja2.FileSystemLoader(searchpath="./app/templates")
        template_env = jinja2.Environment(loader=template_loader)
        template = template_env.get_template("receipt.html")
    except Exception as e:
        logger.error(f"Error loading receipt template: {e}")
        raise e

    # Load Logo
    try:
        with open("./app/templates/logo.svg", "rb") as f:
            logo_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error loading logo: {e}")
        logo_base64 = ""

    # Render HTML template with context
    try:
        html_out = template.render(
            receipt_id=receipt_id,
            payment_id=payment.payment_id,
            date=date_str,
            status=str(payment.status).capitalize(),
            customer_name=payment.payer_name or "N/A",
            customer_phone=payment.payer_phone or "N/A",
            customer_email=payment.payer_email or "",
            amount=float(payment.amount or 0),
            qr_code_base64=qr_base64,
            logo_base64=logo_base64,
        )
    except Exception as e:
        logger.error(f"Error rendering receipt template: {e}")
        raise e

    # Convert HTML to PDF using WeasyPrint
    try:
        HTML(string=html_out).write_pdf(file_path)
    except Exception as e:
        logger.error(f"Error generating PDF from HTML: {e}")
        raise e

    return file_path


@router.get("/payments/receipt/{payment_id}")
def download_receipt(payment_id: str, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if str(payment.status) != "success":
        raise HTTPException(status_code=400, detail="Payment is not successful")

    path = f"receipts/{payment_id}.pdf"
    if not os.path.exists(path):
        create_receipt_pdf(payment)

    return FileResponse(
        path, media_type="application/pdf", filename=f"receipt-{payment_id}.pdf"
    )


@router.get("/payments", response_model=List[PaymentSchema])
def get_payments(db: Session = Depends(get_db)):
    """List all payments."""
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    return payments


@router.get("/payments/transactions", response_model=List[PaymentTransactionSchema])
def get_payment_transactions(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    source: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Return transaction rows shaped for Razorpay-like admin listing.
    """
    limit = max(1, min(limit, 200))
    source_filter = (source or "all").strip().lower()
    if source_filter not in {"all", "gateway", "webhook", "db"}:
        raise HTTPException(status_code=400, detail="Invalid source filter")

    query = db.query(Payment).order_by(Payment.created_at.desc())
    if status:
        query = query.filter(Payment.status == status)
    webhook_order_ids_query = (
        db.query(PaymentWebhookEvent.order_id)
        .filter(PaymentWebhookEvent.order_id.isnot(None))
        .distinct()
    )
    if source_filter == "webhook":
        query = query.filter(Payment.order_id.in_(webhook_order_ids_query))
    elif source_filter == "db":
        query = query.filter(~Payment.order_id.in_(webhook_order_ids_query))

    rows = query.offset(skip).limit(limit).all()
    transactions: List[PaymentTransactionSchema] = []
    has_db_updates = False
    latest_webhook_by_order: Dict[str, PaymentWebhookEvent] = {}

    order_ids = [str(r.order_id) for r in rows if r.order_id is not None]
    if order_ids:
        webhook_rows = (
            db.query(PaymentWebhookEvent)
            .filter(PaymentWebhookEvent.order_id.in_(order_ids))
            .order_by(
                PaymentWebhookEvent.created_at.desc(),
                PaymentWebhookEvent.id.desc(),
            )
            .all()
        )
        for webhook_row in webhook_rows:
            oid = (
                str(webhook_row.order_id)
                if webhook_row.order_id is not None
                else ""
            )
            if oid and oid not in latest_webhook_by_order:
                latest_webhook_by_order[oid] = webhook_row

    for row in rows:
        db_payment_id = str(row.payment_id) if row.payment_id is not None else None
        db_order_id = str(row.order_id) if row.order_id is not None else ""

        latest_webhook = latest_webhook_by_order.get(db_order_id)
        selected_gateway_payment: Optional[Dict[str, Any]] = None
        selected_webhook = latest_webhook

        # Priority: webhook (truth) -> gateway (fallback) -> db.
        if selected_webhook is None and source_filter in {"all", "gateway"}:
            if db_payment_id is not None:
                selected_gateway_payment = _fetch_razorpay_payment(db_payment_id)
            elif db_order_id:
                selected_gateway_payment = _fetch_order_payment(db_order_id)

        normalized = normalize_transaction(
            payment=selected_gateway_payment,
            webhook=selected_webhook,
            db_row=row,
        )

        if source_filter != "all" and normalized["source"] != source_filter:
            continue

        normalized_payment_id = normalized.get("payment_id")
        if normalized_payment_id and db_payment_id is None:
            row.payment_id = str(normalized_payment_id)
            has_db_updates = True

        normalized_status = normalized.get("status")
        if normalized_status == "success" and str(row.status) != "success":
            row.status = "success"
            has_db_updates = True
        elif normalized_status == "failed" and str(row.status) != "failed":
            row.status = "failed"
            has_db_updates = True

        transactions.append(PaymentTransactionSchema(**normalized))

    if has_db_updates:
        db.commit()

    return transactions


@router.get("/payments/webhook-events")
def get_webhook_events(
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = None,
    event: Optional[str] = None,
    order_id: Optional[str] = None,
    payment_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List Razorpay webhook audit events for debugging.
    """
    limit = max(1, min(limit, 200))

    query = db.query(PaymentWebhookEvent).order_by(PaymentWebhookEvent.created_at.desc())

    if status:
        query = query.filter(PaymentWebhookEvent.status == status)
    if event:
        query = query.filter(PaymentWebhookEvent.event == event)
    if order_id:
        query = query.filter(PaymentWebhookEvent.order_id == order_id)
    if payment_id:
        query = query.filter(PaymentWebhookEvent.payment_id == payment_id)

    rows = query.offset(skip).limit(limit).all()
    return [
        {
            "id": row.id,
            "provider": row.provider,
            "event": row.event,
            "status": row.status,
            "reason": row.reason,
            "order_id": row.order_id,
            "payment_id": row.payment_id,
            "signature_valid": row.signature_valid,
            "created_at": row.created_at,
            "payload": row.payload,
        }
        for row in rows
    ]
