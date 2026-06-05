"""Tests for payment analytics series aggregation."""

import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Reuse stub pattern from test_transactions_api
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
_config_mod = types.ModuleType("app.core.config")
_config_mod.settings = _settings
sys.modules["app.core.config"] = _config_mod

_test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(bind=_test_engine, autocommit=False, autoflush=False)

import app.configs.db_config as _db_cfg  # noqa: E402

_db_cfg.mysql_engine = _test_engine
_db_cfg.MySQLSessionLocal = _TestSession

from app.models.payment import Payment  # noqa: E402
import app.models.realty  # noqa: E402, F401
from app.models.booking import Booking  # noqa: E402, F401
from app.models.realty import Property  # noqa: E402
from app.services.payment_analytics import payment_analytics_series  # noqa: E402

Payment.__table__.metadata.create_all(bind=_test_engine)


@pytest.fixture(autouse=True)
def _clean():
    db = _TestSession()
    db.query(Booking).delete()
    db.query(Payment).delete()
    db.query(Property).delete()
    db.commit()
    db.close()
    yield


def test_analytics_series_monthly_points_ordered():
    db = _TestSession()
    p1 = Payment(
        order_id="o1",
        amount=100.0,
        currency="INR",
        status="success",
        payment_type="booking",
    )
    p1.created_at = datetime(2026, 5, 5, tzinfo=timezone.utc)
    p2 = Payment(
        order_id="o2",
        amount=200.0,
        currency="INR",
        status="success",
        payment_type="booking",
    )
    p2.created_at = datetime(2026, 5, 20, tzinfo=timezone.utc)
    db.add_all([p1, p2])
    db.commit()

    result = payment_analytics_series(db, granularity="monthly", month="2026-05")
    assert result["granularity"] == "monthly"
    assert len(result["points"]) >= 1
    assert result["points"][0]["revenue"] == 300.0
    assert result["status_breakdown"]["success"] == 2
    db.close()
