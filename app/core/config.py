import os
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    ENV: str = "production"
    # Comma-separated extra browser origins for CORS (e.g. staging admin URL).
    CORS_EXTRA_ORIGINS: str = ""
    # Dev-only: run SQLAlchemy create_all on startup. Production should use Alembic only.
    SQLALCHEMY_CREATE_ALL_ON_STARTUP: bool = False
    # Set true only when debugging SQL (prints every query — very noisy during Housing sync).
    SQLALCHEMY_ECHO: bool = False
    SENTRY_DSN: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379"

    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    CLOUDFRONT_DOMAIN: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None
    # If true, HEAD the object before persisting property_images; optional override / strict modes below.
    S3_VERIFY_UPLOAD_CONTENT_TYPE_WITH_HEAD: bool = False
    # When HEAD succeeds and S3 Content-Type is an allowed image/*, prefer it over URL-derived MIME.
    S3_HEAD_VERIFY_OVERRIDE_DB_FROM_S3: bool = True
    # If true and S3 Content-Type disagrees with URL-derived MIME and override did not apply: mime_validated=False.
    S3_HEAD_MISMATCH_STRICT: bool = False
    # If true and mismatch remains after override check: delete S3 object and return 400 (no DB row).
    S3_HEAD_MISMATCH_DELETE_OBJECT: bool = False
    # When delete-on-mismatch is enabled, require two agreeing HEAD results before delete (reduces flaky deletes).
    S3_HEAD_DELETE_REQUIRES_DOUBLE_CONFIRM: bool = True
    # HEAD retries (transient errors / empty metadata).
    S3_HEAD_MAX_ATTEMPTS: int = 3
    S3_HEAD_RETRY_BASE_SECONDS: float = 0.5
    # Optional: Range GET first bytes + libmagic (requires python-magic + system libmagic).
    S3_VERIFY_MAGIC_FROM_BYTES: bool = False
    S3_MAGIC_RANGE_BYTES: int = 8192

    # Orphan uploads/ cleanup (APScheduler daily job)
    S3_ORPHAN_CLEANUP_ENABLED: bool = False
    S3_ORPHAN_CLEANUP_DRY_RUN: bool = True
    S3_ORPHAN_CLEANUP_MIN_AGE_HOURS: int = 48
    # Extra minutes added to min age (staging tuning); production keep 0 and rely on hours.
    S3_ORPHAN_CLEANUP_MIN_AGE_MINUTES: int = 0
    S3_ORPHAN_CLEANUP_MAX_DELETES_PER_RUN: int = 500
    # Log / webhook alert if non-dry-run deletes in one run exceed this (0 = disabled).
    S3_ORPHAN_CLEANUP_ALERT_DELETES_THRESHOLD: int = 100

    # Optional POST JSON alerts (Slack-compatible webhook, etc.)
    ALERT_WEBHOOK_URL: Optional[str] = None
    S3_ORPHAN_CLEANUP_CRON_HOUR_UTC: int = 3
    S3_ORPHAN_CLEANUP_CRON_MINUTE_UTC: int = 15

    # CloudFront Configuration
    CLOUDFRONT_KEY_PAIR_ID: Optional[str] = None
    CLOUDFRONT_PRIVATE_KEY: Optional[str] = None

    # Razorpay
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Authentication
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200

    # Email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_PORT: int
    MAIL_SERVER: str
    MAIL_FROM_NAME: str

    # IMAP Configuration (for Email Fallback Ingestion)
    IMAP_SERVER: str = ""
    IMAP_PORT: int = 993
    IMAP_USERNAME: str = ""
    IMAP_PASSWORD: str = ""
    EMAIL_POLL_INTERVAL_MINUTES: int = 5

    # Zoho CRM
    ZOHO_CRM_CLIENT_ID: str = ""
    ZOHO_CRM_CLIENT_SECRET: str = ""
    ZOHO_CRM_REFRESH_TOKEN: str = ""
    # API field name in Zoho Leads module for budget (create custom field in Zoho if needed).
    ZOHO_CRM_BUDGET_FIELD: str = "Budget"
    # Use exact API names from Zoho → Setup → Modules → Leads → Fields. Override if your org uses __c custom fields.
    ZOHO_CRM_PREFERRED_LOCATION_FIELD: str = "Preferred_Location__c"
    ZOHO_CRM_LEAD_TYPE_FIELD: str = "Lead_Type__c"
    ZOHO_CRM_INQUIRY_COUNT_FIELD: str = "Inquiry_Count"
    # JSON map of city/area keyword → employees.id (PK) for auto RM assignment, e.g. {"BTM": 1, "HSR": 2}
    CRM_CITY_EMPLOYEE_JSON: str = "{}"
    # Redis-backed daily Zoho HTTP counter; 0 = disable guard. Soft limit = ratio × budget.
    ZOHO_DAILY_API_BUDGET: int = 10_000
    ZOHO_DAILY_API_SOFT_LIMIT_RATIO: float = 0.8
    # Celery duplicate-task idempotency: skip if last success within this window (seconds).
    ZOHO_SYNC_IDEMPOTENCY_SECONDS: int = 120
    # If another worker set crm_status=processing within this window, retry later.
    ZOHO_PROCESSING_CONFLICT_SECONDS: float = 90.0
    # If stuck in processing longer than this, allow takeover.
    ZOHO_PROCESSING_STALE_SECONDS: float = 300.0
    # Celery default-queue depth; log error when exceeded (requires celery beat for periodic check).
    CELERY_QUEUE_BACKLOG_ALERT_THRESHOLD: int = 1000
    # Extra countdown (seconds) for Zoho sync enqueues when queue depth > threshold.
    CELERY_BACKPRESSURE_DELAY_SECONDS: int = 120
    # Rolling window: open circuit when failure ratio in last N outcomes >= this (requires Redis).
    ZOHO_CIRCUIT_FAILURE_RATIO: float = 0.5
    ZOHO_CIRCUIT_PAUSE_SECONDS: int = 300
    # GET /api/v1/internal/zoho-status — set in production; empty = endpoint returns 404.
    INTERNAL_METRICS_TOKEN: str = ""

    # Retell AI
    RETELL_API_KEY: str = ""
    RETELL_AGENT_ID: str = ""
    RETELL_FROM_NUMBER: str = ""

    # Twilio WhatsApp
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    # e.g. "whatsapp:+919187201191"
    TWILIO_WHATSAPP_FROM: str = ""
    # Approved template SID (content SID), e.g. "HX..."
    TWILIO_WHATSAPP_TEMPLATE_SID: str = ""

    # Optional fallback template for when free-form WhatsApp replies fail
    # (for example, outside the 24h customer-care window).
    TWILIO_WHATSAPP_FALLBACK_TEMPLATE_SID: str = ""

    # Meta WhatsApp Cloud (interactive messages + list/buttons)
    WHATSAPP_TOKEN: str = ""
    PHONE_NUMBER_ID: str = ""
    VERIFY_TOKEN: str = ""
    META_GRAPH_API_VERSION: str = "v18.0"

    # Webhook
    ZOHO_WEBHOOK_SECRET: str = ""
    # The phone number (with country code, e.g. +91...) to receive Hot Lead / Deal alerts
    SALES_TEAM_PHONE: str = "+910000000000"
    # Required for Zoho HMAC verification
    HOUSING_WEBHOOK_API_KEY: str = ""
    ENABLE_AI_CALLING_FOR_LEADS: bool = True
    # Log first N bytes of raw 99acres POST body (debugging; avoid huge logs in prod).
    WEBHOOK_LOG_BODY_MAX: int = 50_000
    # If True, return HTTP 500 when any <Qry> in a batch fails (may trigger full batch retry from provider).
    WEBHOOK_99ACRES_HTTP_500_ON_ANY_QRY_FAILURE: bool = False

    # Housing API
    HOUSING_API_KEY: str = ""
    HOUSING_API_ID: str = ""
    HOUSING_SYNC_INTERVAL_SECONDS: int = 30
    # Default off: local uvicorn avoids Housing/99acres polling (MySQL load + pool contention with API).
    # Production: set true in .env.production or ecosystem.config.js (PM2).
    LEAD_PULL_SYNC_ENABLED: bool = False
    LEAD_DAILY_SYNC_ENABLED: bool = True
    LEAD_DAILY_SYNC_HOUR_UTC: int = 2
    LEAD_DAILY_SYNC_MINUTE_UTC: int = 0

    # 99acres Pull API
    # Obtain ACRES_API_KEY from your 99acres account manager.
    # Without it the pull sync gracefully no-ops; webhook push still works.
    ACRES_API_KEY: str = ""
    ACRES_API_URL: str = "https://www.99acres.com/api/fetch-leads"
    ACRES_SYNC_INTERVAL_SECONDS: int = 120  # default: every 2 minutes

    # Alerting (Slack/Discord/Webhook)
    ALERT_WEBHOOK_URL: str = ""

    # Load env files in increasing priority (later files override earlier ones).
    # This makes local development work out-of-the-box (e.g. DB on a different port)
    # while still supporting environment-specific files when ENV is exported.
    _env = os.getenv("ENV")
    _env_files = [".env", ".env.local"]
    if _env:
        _env_files.extend([f".env.{_env}", f".env.{_env}.local"])

    model_config = {"env_file": tuple(_env_files), "extra": "allow"}

settings = Settings()
