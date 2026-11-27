"""
Integration tests for GET /api/v1/payments/transactions

Uses an in-memory SQLite database so the tests run fully offline —
no MySQL, no Razorpay, no env-file required.

What is exercised:
- `source` field values (webhook / db / gateway) on response rows
- `status` field: authorized → pending, captured → success
- `bank_rrn` propagated from webhook payload via acquirer_data.rrn
- `created_at` falls back to DB value when gateway timestamp is absent
- source-filter query param (?source=webhook, ?source=db)
- `sync_from_gateway` reconciles pending rows without webhook rows (Razorpay order/payments)
"""

import json
import os
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# Minimal stubs for heavy optional dependencies the API module imports at
# module-load time.  We insert them before any app code is imported.
# ---------------------------------------------------------------------------

_INSERTED_STUBS = []


def _stub(name: str, **attrs) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    _INSERTED_STUBS.append(name)
    return mod



class _RazorpayUtility:
    def verify_payment_signature(self, *a, **kw):
        pass


class _RazorpayClient:
    def __init__(self, *a, **kw):
        self.utility = _RazorpayUtility()


class _SigError(Exception):
    pass


_rz = _stub("razorpay", Client=_RazorpayClient)
_rz.errors = SimpleNamespace(SignatureVerificationError=_SigError)

_stub("jinja2",
      FileSystemLoader=type("FL", (), {}),
      Environment=type("Env", (), {}))

_stub("qrcode", make=lambda *a, **kw: SimpleNamespace(save=lambda *a, **kw: None))
_stub("weasyprint", HTML=type("HTML", (), {"write_pdf": lambda self, *a, **kw: None}))

# Stub app.core.config with a pre-built settings object so db_config never
# touches pydantic_settings or a real .env file.
_settings = SimpleNamespace(
    DB_HOST="localhost",
    DB_PORT=3306,
    DB_USER="test",
    DB_PASSWORD="test",
    DB_NAME="test",
    SECRET_KEY="test-secret",
    ALGORITHM="HS256",
    ACCESS_TOKEN_EXPIRE_MINUTES=43200,
    MAIL_USERNAME="test@example.com",
    MAIL_PASSWORD="test",
    MAIL_FROM="test@example.com",
    MAIL_PORT=587,
    MAIL_SERVER="smtp.example.com",
    MAIL_FROM_NAME="Test",
    RAZORPAY_KEY_ID="",
    RAZORPAY_KEY_SECRET="",
    RAZORPAY_WEBHOOK_SECRET="test_secret",
    REDIS_URL="redis://localhost:6379",
    ENV="test",
    SENTRY_DSN=None,
    AWS_ACCESS_KEY_ID=None,
    AWS_SECRET_ACCESS_KEY=None,
    AWS_REGION=None,
    S3_BUCKET_NAME=None,
    CLOUDFRONT_DOMAIN=None,
    CLOUDFRONT_KEY_PAIR_ID=None,
    CLOUDFRONT_PRIVATE_KEY=None,
    S3_VERIFY_UPLOAD_CONTENT_TYPE_WITH_HEAD=False,
    S3_HEAD_VERIFY_OVERRIDE_DB_FROM_S3=True,
    S3_HEAD_MISMATCH_STRICT=False,
    S3_HEAD_MISMATCH_DELETE_OBJECT=False,
    S3_HEAD_DELETE_REQUIRES_DOUBLE_CONFIRM=True,
    S3_HEAD_MAX_ATTEMPTS=3,
    S3_HEAD_RETRY_BASE_SECONDS=0.5,
    S3_VERIFY_MAGIC_FROM_BYTES=False,
    S3_MAGIC_RANGE_BYTES=8192,
    ALERT_WEBHOOK_URL=None,
    S3_ORPHAN_CLEANUP_ENABLED=False,
    S3_ORPHAN_CLEANUP_DRY_RUN=True,
    S3_ORPHAN_CLEANUP_MIN_AGE_HOURS=48,
    S3_ORPHAN_CLEANUP_MIN_AGE_MINUTES=0,
    S3_ORPHAN_CLEANUP_MAX_DELETES_PER_RUN=500,
    S3_ORPHAN_CLEANUP_ALERT_DELETES_THRESHOLD=100,
    S3_ORPHAN_CLEANUP_CRON_HOUR_UTC=3,
    S3_ORPHAN_CLEANUP_CRON_MINUTE_UTC=15,
    ZOHO_CRM_CLIENT_ID="",
    ZOHO_CRM_CLIENT_SECRET="",
    ZOHO_CRM_REFRESH_TOKEN="",
    RETELL_API_KEY="",
    RETELL_AGENT_ID="",
    RETELL_FROM_NUMBER="",
    TWILIO_ACCOUNT_SID="",
    TWILIO_AUTH_TOKEN="",
    TWILIO_WHATSAPP_FROM="",
    TWILIO_WHATSAPP_TEMPLATE_SID="",
    TWILIO_WHATSAPP_FALLBACK_TEMPLATE_SID="",
    WHATSAPP_TOKEN="",
    PHONE_NUMBER_ID="",
    VERIFY_TOKEN="",
    META_GRAPH_API_VERSION="v18.0",
    HOUSING_WEBHOOK_API_KEY="",
    ENABLE_AI_CALLING_FOR_LEADS=False,
    HOUSING_API_KEY="",
    HOUSING_API_ID="",
    HOUSING_SYNC_INTERVAL_SECONDS=120,
    SQLALCHEMY_ECHO=False,
)
_prev_config_mod = sys.modules.get("app.core.config")
_config_mod = types.ModuleType("app.core.config")
_config_mod.settings = _settings
_config_mod.validate_startup_settings = lambda *_a, **_kw: None
_config_mod.load_app_env = lambda *_a, **_kw: ()
if "app.core.config" not in sys.modules:
    sys.modules["app.core.config"] = _config_mod

# ---------------------------------------------------------------------------
# Bootstrap a minimal in-memory SQLite database and swap out get_db so the
# API endpoints use it instead of the real MySQL connection.
# ---------------------------------------------------------------------------

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# StaticPool keeps every caller on the same underlying connection, so the
# in-memory database is never discarded between test helper calls and HTTP
# requests served by the TestClient.
_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_test_engine, autocommit=False, autoflush=False)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


# Patch db_config to point at SQLite before any model/router imports
import app.configs.db_config as _db_cfg  # noqa: E402

_db_cfg.mysql_engine = _test_engine
_db_cfg.MySQLSessionLocal = _TestSession
_db_cfg.SessionLocal = _TestSession
_db_cfg.get_db = _override_get_db
_db_cfg.get_mysql_db = _override_get_db

# Import models — they are already registered on MySQLBase.metadata
from app.models.payment import Payment  # noqa: E402
from app.models.payment_webhook_event import PaymentWebhookEvent  # noqa: E402

# Booking model references "Property" via relationship; import realty models
# first so SQLAlchemy mapper can resolve the name.
import app.models.realty  # noqa: E402, F401
from app.models.booking import Booking  # noqa: E402, F401

# Create tables on SQLite using the exact metadata the models are bound to
Payment.__table__.metadata.create_all(bind=_test_engine)

# Import the FastAPI router and build a minimal test app
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.api.payment import router as payment_router  # noqa: E402

for _stub_name in _INSERTED_STUBS:
    sys.modules.pop(_stub_name, None)

if _prev_config_mod is None:
    sys.modules.pop("app.core.config", None)
else:
    sys.modules["app.core.config"] = _prev_config_mod

_app = FastAPI()
_app.include_router(payment_router, prefix="/api/v1")
_app.dependency_overrides = {}

# Override get_db in the payment router's dependency
from app.configs.db_config import get_db  # noqa: E402

_app.dependency_overrides[get_db] = _override_get_db

# Transaction endpoints are admin-only; authenticate the test client as staff.
from app.core import security as _security  # noqa: E402

_app.dependency_overrides[_security.admin_or_employee_required] = lambda: type(
    "StaffUser", (), {"id": 1, "email": "staff@test", "role": "admin"}
)()

client = TestClient(_app, raise_server_exceptions=True)


def _items(body):
    """Paginated list response or legacy bare array."""
    if isinstance(body, dict) and "items" in body:
        return body["items"], body.get("total", len(body["items"]))
    return body, len(body)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payment(db, **overrides) -> Payment:
    defaults = dict(
        order_id="order_integ_1",
        amount=500.0,
        currency="INR",
        status="pending",
        payment_type="booking",
        payer_name="Integ User",
        payer_email="integ@example.com",
        payer_phone="9876543210",
    )
    defaults.update(overrides)
    p = Payment(**defaults)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_webhook(db, order_id: str, event: str, payment_entity: dict) -> PaymentWebhookEvent:
    payload = {"payload": {"payment": {"entity": payment_entity}}}
    w = PaymentWebhookEvent(
        provider="razorpay",
        event=event,
        status="processed",
        order_id=order_id,
        payment_id=payment_entity.get("id"),
        signature_valid=True,
        payload=payload,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture(autouse=True)
def _clean_db():
    """Truncate both tables before every test."""
    db = _TestSession()
    db.query(PaymentWebhookEvent).delete()
    db.query(Payment).delete()
    db.commit()
    db.close()
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_transactions_returns_db_source_when_no_webhook():
    db = _TestSession()
    _make_payment(db, order_id="order_db_only")
    db.close()

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, total = _items(r.json())
    assert total == 1
    assert len(rows) == 1
    assert rows[0]["source"] == "db"
    assert rows[0]["order_id"] == "order_db_only"


def test_transactions_webhook_source_and_status_captured_becomes_success():
    db = _TestSession()
    _make_payment(db, order_id="order_wh_1", status="pending")
    _make_webhook(db, "order_wh_1", "payment.captured", {
        "id": "pay_wh_1",
        "order_id": "order_wh_1",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
    })
    db.close()

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "webhook"
    assert row["status"] == "success"
    assert row["payment_id"] == "pay_wh_1"


def test_transactions_authorized_status_is_pending_not_success():
    db = _TestSession()
    _make_payment(db, order_id="order_auth_1", status="pending")
    _make_webhook(db, "order_auth_1", "payment.authorized", {
        "id": "pay_auth_1",
        "order_id": "order_auth_1",
        "amount": 50000,
        "status": "authorized",
        "currency": "INR",
    })
    db.close()

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert rows[0]["status"] == "pending"


def test_transactions_bank_rrn_from_webhook_acquirer_data():
    db = _TestSession()
    _make_payment(db, order_id="order_rrn_1", status="pending")
    _make_webhook(db, "order_rrn_1", "payment.captured", {
        "id": "pay_rrn_1",
        "order_id": "order_rrn_1",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
        "acquirer_data": {"rrn": "RRN9876543"},
    })
    db.close()

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert rows[0]["bank_rrn"] == "RRN9876543"


def test_transactions_bank_rrn_fallback_to_upi_transaction_id():
    db = _TestSession()
    _make_payment(db, order_id="order_rrn_2", status="pending")
    _make_webhook(db, "order_rrn_2", "payment.captured", {
        "id": "pay_rrn_2",
        "order_id": "order_rrn_2",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
        "acquirer_data": {"upi_transaction_id": "UPI12345"},
    })
    db.close()

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert rows[0]["bank_rrn"] == "UPI12345"


def test_transactions_source_filter_webhook_only():
    db = _TestSession()
    _make_payment(db, order_id="order_filter_wh", status="pending")
    _make_payment(db, order_id="order_filter_db", status="pending")
    _make_webhook(db, "order_filter_wh", "payment.captured", {
        "id": "pay_filter_1",
        "order_id": "order_filter_wh",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
    })
    db.close()

    r = client.get("/api/v1/payments/transactions?source=webhook")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert len(rows) == 1
    assert rows[0]["order_id"] == "order_filter_wh"
    assert rows[0]["source"] == "webhook"


def test_transactions_source_filter_db_only():
    db = _TestSession()
    _make_payment(db, order_id="order_filter_wh2", status="pending")
    _make_payment(db, order_id="order_filter_db2", status="pending")
    _make_webhook(db, "order_filter_wh2", "payment.captured", {
        "id": "pay_filter_2",
        "order_id": "order_filter_wh2",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
    })
    db.close()

    r = client.get("/api/v1/payments/transactions?source=db")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert all(row["source"] == "db" for row in rows)
    order_ids = [row["order_id"] for row in rows]
    assert "order_filter_db2" in order_ids
    assert "order_filter_wh2" not in order_ids


def test_transactions_sync_from_gateway_reconciles_pending_without_webhook(monkeypatch):
    """When no webhook exists, optional Razorpay order/payments fetch fills capture state."""
    db = _TestSession()
    _make_payment(db, order_id="order_gw_recon", status="pending")
    db.close()

    captured = {
        "id": "pay_gw_recon_1",
        "order_id": "order_gw_recon",
        "amount": 100000,
        "status": "captured",
        "currency": "INR",
        "created_at": 1700000000,
        "method": "upi",
    }

    def fake_fetch(order_id: str):
        return captured if order_id == "order_gw_recon" else None

    monkeypatch.setattr("app.api.payment._fetch_order_payment", fake_fetch)

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "gateway"
    assert row["status"] == "success"
    assert row["payment_id"] == "pay_gw_recon_1"

    db2 = _TestSession()
    p = db2.query(Payment).filter(Payment.order_id == "order_gw_recon").one()
    assert p.status == "success"
    assert p.payment_id == "pay_gw_recon_1"
    db2.close()


def test_transactions_paginated_response_shape():
    db = _TestSession()
    for i in range(3):
        _make_payment(db, order_id=f"order_page_{i}")
    db.close()

    r = client.get("/api/v1/payments/transactions?skip=0&limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert body["skip"] == 0
    assert body["limit"] == 2
    assert len(body["items"]) == 2


def test_transactions_month_filter():
    db = _TestSession()
    _make_payment(
        db,
        order_id="order_may",
        status="success",
        amount=1000.0,
    )
    p_may = db.query(Payment).filter(Payment.order_id == "order_may").one()
    p_may.created_at = datetime(2026, 5, 15, 12, 0, 0, tzinfo=timezone.utc)
    _make_payment(
        db,
        order_id="order_apr",
        status="success",
        amount=2000.0,
    )
    p_apr = db.query(Payment).filter(Payment.order_id == "order_apr").one()
    p_apr.created_at = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    db.commit()
    db.close()

    r = client.get("/api/v1/payments/transactions?month=2026-05")
    assert r.status_code == 200
    rows, total = _items(r.json())
    assert total == 1
    assert rows[0]["order_id"] == "order_may"


def test_transactions_gst_and_property_from_booking():
    from app.models.realty import Property

    db = _TestSession()
    prop = Property(
        property_name="HSR PG Alpha",
        city="Bangalore",
        listing_type="rent",
    )
    db.add(prop)
    db.flush()
    _make_payment(db, order_id="order_prop_1", status="success", amount=1180.0)
    booking = Booking(
        order_id="order_prop_1",
        property_id=prop.id,
        customer_name="Tenant",
        amount=1180.0,
    )
    db.add(booking)
    db.commit()
    db.close()

    r = client.get("/api/v1/payments/transactions")
    assert r.status_code == 200
    rows, _ = _items(r.json())
    assert rows[0]["property_name"] == "HSR PG Alpha"
    assert rows[0]["property_city"] == "Bangalore"
    assert rows[0]["gst_amount"] == 180.0


def test_transaction_detail_with_timeline():
    db = _TestSession()
    _make_payment(db, order_id="order_detail_1", status="pending")
    _make_webhook(db, "order_detail_1", "payment.captured", {
        "id": "pay_detail_1",
        "order_id": "order_detail_1",
        "amount": 50000,
        "status": "captured",
        "currency": "INR",
    })
    db.close()

    r = client.get("/api/v1/payments/transactions/order_detail_1")
    assert r.status_code == 200
    body = r.json()
    assert body["transaction"]["order_id"] == "order_detail_1"
    assert len(body["timeline"]) >= 1
