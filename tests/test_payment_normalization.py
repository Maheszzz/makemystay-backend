from datetime import datetime, timezone
from types import SimpleNamespace
from app.services.payment_normalization import _map_status, normalize_transaction


def _db_row(**overrides):
    base = {
        "id": 1,
        "payment_id": None,
        "order_id": "order_db_1",
        "amount": 500.0,
        "status": "pending",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "payer_email": "db@example.com",
        "payer_phone": "9999999999",
        "payer_name": "DB User",
        "payment_type": "booking",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_map_status_authorized_and_created_are_pending():
    assert _map_status("authorized") == "pending"
    assert _map_status("created") == "pending"
    assert _map_status("captured") == "success"


def test_source_falls_back_to_gateway_when_webhook_without_payment_entity():
    row = _db_row(order_id="order_fallback_1")
    webhook = SimpleNamespace(
        payload={"payload": {"payment": {}}},  # webhook exists but has no payment entity
        event="payment.captured",
    )
    gateway_payment = {
        "id": "pay_gateway_1",
        "order_id": "order_fallback_1",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
    }

    normalized = normalize_transaction(payment=gateway_payment, webhook=webhook, db_row=row)

    assert normalized["source"] == "gateway"
    assert normalized["payment_id"] == "pay_gateway_1"
    assert normalized["status"] == "success"


def test_created_at_none_uses_db_timestamp():
    db_created_at = datetime(2026, 2, 2, tzinfo=timezone.utc)
    row = _db_row(created_at=db_created_at)
    gateway_payment = {
        "id": "pay_created_none",
        "order_id": "order_db_1",
        "amount": 50000,
        "status": "created",
        "created_at": None,
        "currency": "INR",
    }

    normalized = normalize_transaction(payment=gateway_payment, db_row=row)

    assert normalized["created_at"] == db_created_at
    assert normalized["status"] == "pending"


def test_bank_rrn_uses_acquirer_rrn_then_fallback_keys():
    row = _db_row()

    with_rrn = {
        "id": "pay_rrn_1",
        "order_id": "order_db_1",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
        "acquirer_data": {"rrn": "RRN12345", "upi_transaction_id": "UPI999"},
    }
    normalized_with_rrn = normalize_transaction(payment=with_rrn, db_row=row)
    assert normalized_with_rrn["bank_rrn"] == "RRN12345"

    with_fallback_only = {
        "id": "pay_rrn_2",
        "order_id": "order_db_1",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
        "acquirer_data": {"upi_transaction_id": "UPI999"},
    }
    normalized_with_fallback = normalize_transaction(payment=with_fallback_only, db_row=row)
    assert normalized_with_fallback["bank_rrn"] == "UPI999"

