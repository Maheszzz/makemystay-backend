from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _extract_bank_rrn(payment_payload: Dict[str, Any]) -> Optional[str]:
    acquirer_data = payment_payload.get("acquirer_data") or {}
    keys = [
        "rrn",
        "upi_transaction_id",
        "bank_transaction_id",
        "bank_ref_num",
        "reference16",
        "arn",
    ]
    for key in keys:
        value = acquirer_data.get(key)
        if value:
            return str(value)
    return None


def _map_status(status: Optional[str]) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"captured", "paid", "success"}:
        return "success"
    if normalized in {"authorized", "created"}:
        return "pending"
    if normalized in {"failed", "failure"}:
        return "failed"
    return "pending"


def normalize_transaction(
    *,
    payment: Optional[Dict[str, Any]] = None,
    webhook: Optional[Any] = None,
    db_row: Optional[Any] = None,
) -> Dict[str, Any]:
    # Priority: webhook > gateway > db
    payment_data: Dict[str, Any] = {}
    if webhook:
        webhook_payload_dict = webhook.payload if isinstance(webhook.payload, dict) else {}
        if "payload" in webhook_payload_dict:
            payment_data = webhook_payload_dict.get("payload", {}).get("payment", {}).get("entity", {})
        else:
            payment_data = webhook_payload_dict.get("payment", {}).get("entity", {})

    if webhook and payment_data:
        source = "webhook"
    elif payment:
        source = "gateway"
        payment_data = payment
    else:
        source = "db"

    payment_id = payment_data.get("id") or db_row.payment_id if db_row else None
    order_id = payment_data.get("order_id") or db_row.order_id if db_row else ""

    amount_raw = payment_data.get("amount")
    if amount_raw is not None:
        amount = float(amount_raw) / 100
    else:
        amount = float(db_row.amount) if db_row and db_row.amount is not None else 0.0

    raw_status = payment_data.get("status") or (webhook.event if webhook else None) or (db_row.status if db_row else "pending")
    status = _map_status(raw_status)
    db_status = _map_status(db_row.status if db_row else "pending")

    created_at_val = payment_data.get("created_at")
    if isinstance(created_at_val, int):
        created_at = datetime.fromtimestamp(created_at_val, tz=timezone.utc)
    else:
        created_at = db_row.created_at if db_row else None

    method = payment_data.get("method")
    customer_email = payment_data.get("email") or (db_row.payer_email if db_row else None)
    customer_phone = payment_data.get("contact") or (db_row.payer_phone if db_row else None)
    customer_name = payment_data.get("name") or payment_data.get("notes", {}).get("name") or (db_row.payer_name if db_row else None)
    bank_rrn = (
        payment_data.get("acquirer_data", {}).get("rrn")
        or _extract_bank_rrn(payment_data)
    )

    return {
        "id": db_row.id if db_row else None,
        "payment_id": payment_id,
        "order_id": order_id,
        "amount": amount,
        "currency": payment_data.get("currency", "INR"),
        "status": status,
        "db_status": db_status,
        "method": method,
        "customer_name": customer_name,
        "customer_email": customer_email,
        "customer_phone": customer_phone,
        "bank_rrn": bank_rrn,
        "created_at": created_at,
        "payment_type": db_row.payment_type if db_row else None,
        "detail_url": f"https://dashboard.razorpay.com/app/payments/{payment_id}" if payment_id else None,
        "source": source,
    }

