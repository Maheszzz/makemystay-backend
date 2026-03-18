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

    # Zoho CRM
    ZOHO_CRM_CLIENT_ID: str = ""
    ZOHO_CRM_CLIENT_SECRET: str = ""
    ZOHO_CRM_REFRESH_TOKEN: str = ""

    # Retell AI
    RETELL_API_KEY: str = ""
    RETELL_AGENT_ID: str = ""
    RETELL_FROM_NUMBER: str = ""

    # Webhook
    HOUSING_WEBHOOK_API_KEY: str = ""
    ENABLE_AI_CALLING_FOR_LEADS: bool = True

    # Housing API
    HOUSING_API_KEY: str = ""
    HOUSING_API_ID: str = ""
    HOUSING_SYNC_INTERVAL_SECONDS: int = 120

    model_config = {
        "env_file": (".env", f".env.{os.getenv('ENV', 'dev')}"),
        "extra": "allow"
    }

settings = Settings()
