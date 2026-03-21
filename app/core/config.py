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
    SENTRY_DSN: Optional[str] = None
    REDIS_URL: str = "redis://localhost:6379"

    # AWS
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    CLOUDFRONT_DOMAIN: Optional[str] = None
    S3_BUCKET_NAME: Optional[str] = None

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
    HOUSING_WEBHOOK_API_KEY: str = ""
    ENABLE_AI_CALLING_FOR_LEADS: bool = True

    # Housing API
    HOUSING_API_KEY: str = ""
    HOUSING_API_ID: str = ""
    HOUSING_SYNC_INTERVAL_SECONDS: int = 30
    LEAD_DAILY_SYNC_ENABLED: bool = True
    LEAD_DAILY_SYNC_HOUR_UTC: int = 2
    LEAD_DAILY_SYNC_MINUTE_UTC: int = 0

    # Load env files in increasing priority (later files override earlier ones).
    # This makes local development work out-of-the-box (e.g. DB on a different port)
    # while still supporting environment-specific files when ENV is exported.
    _env = os.getenv("ENV")
    _env_files = [".env", ".env.local"]
    if _env:
        _env_files.extend([f".env.{_env}", f".env.{_env}.local"])

    model_config = {"env_file": tuple(_env_files), "extra": "allow"}

settings = Settings()
