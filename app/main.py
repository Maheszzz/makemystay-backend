"""FastAPI application for Realty API."""

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import time
from collections import defaultdict

from app.core.config import settings
from app.core.log_dedupe import should_log_once

# --- Settings & Logging ---
load_dotenv()
# Reload marker (forces dev server reload when env changes) v2
logging.basicConfig(level=logging.INFO)
logger.info(f"ENV={settings.ENV}")

failed_logins = defaultdict(list)

def security_alerter(message):
    try:
        msg_str = message.record["message"]
        if "LOGIN_FAILED:" in msg_str:
            email = msg_str.split("LOGIN_FAILED: ")[-1].strip()
            now = time.time()
            failed_logins[email].append(now)
            failed_logins[email] = [t for t in failed_logins[email] if now - t < 60]
            if len(failed_logins[email]) >= 10:
                logger.error(f"SECURITY ALERT: >10 failed logins for {email} detected in 60s!")
                failed_logins[email].clear()
    except Exception as e:
        pass

logger.add(security_alerter, filter=lambda record: "audit" in record["extra"])

# --- Rate Limiter ---
from app.core.rate_limit import limiter

# --- Background Scheduler ---
import asyncio
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.lead_sync_service import sync_all_sources, sync_daily_recovery
from app.services.email_service import sync_emails_job

scheduler = BackgroundScheduler()
THROTTLED_ERROR_ENDPOINTS = {"/api/v1/admin/analytics", "/api/v1/realty/properties"}

# --- Sentry Setup ---
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENV,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    logger.info("Sentry initialization complete")

def sync_all_job():
    """APScheduler wrapper for the unified sync function."""
    asyncio.run(sync_all_sources())


def daily_recovery_sync_job():
    """Daily safety-net sync for last 24h lead window."""
    asyncio.run(sync_daily_recovery())

def email_sync_wrapper_job():
    """APScheduler wrapper for the IMAP email sync function."""
    asyncio.run(sync_emails_job())

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the app."""
    logger.info("Starting background scheduler...")
    # Single registration: fires immediately on startup AND repeats on interval
    scheduler.add_job(
        sync_all_job,
        "interval",
        seconds=settings.HOUSING_SYNC_INTERVAL_SECONDS,
        id="sync_all_job",
        next_run_time=datetime.now(),
    )
    if settings.LEAD_DAILY_SYNC_ENABLED:
        scheduler.add_job(
            daily_recovery_sync_job,
            "cron",
            hour=settings.LEAD_DAILY_SYNC_HOUR_UTC,
            minute=settings.LEAD_DAILY_SYNC_MINUTE_UTC,
            id="daily_recovery_sync_job",
        )

    if getattr(settings, "EMAIL_POLL_INTERVAL_MINUTES", 0) > 0:
        scheduler.add_job(
            email_sync_wrapper_job,
            "interval",
            minutes=settings.EMAIL_POLL_INTERVAL_MINUTES,
            id="email_sync_job",
            next_run_time=datetime.now(),
        )

    scheduler.start()
    logger.info(
        f"APScheduler started: sync_all_job every {settings.HOUSING_SYNC_INTERVAL_SECONDS}s"
    )
    if settings.LEAD_DAILY_SYNC_ENABLED:
        logger.info(
            "Daily recovery sync enabled at "
            f"{settings.LEAD_DAILY_SYNC_HOUR_UTC:02d}:{settings.LEAD_DAILY_SYNC_MINUTE_UTC:02d} UTC"
        )
    if getattr(settings, "EMAIL_POLL_INTERVAL_MINUTES", 0) > 0:
        logger.info(f"Email sync job scheduled every {settings.EMAIL_POLL_INTERVAL_MINUTES}m")
    yield
    logger.info("Shutting down background scheduler...")
    scheduler.shutdown()

# --- FastAPI App ---
app = FastAPI(
    title="Realty API",
    description="API for managing property listings and contacts",
    version="1.0.0",
    lifespan=lifespan
)

# Initialize Prometheus metrics
Instrumentator().instrument(app).expose(app)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- Middleware ---
# Configure CORS for frontend connection
# (no-op) This comment exists to trigger uvicorn reload in local development.
if settings.ENV == "production":
    allowed_origins = [
        "https://makemystay.ai",
        "https://www.makemystay.ai",
        "https://admin.makemystay.ai",
        "https://api.makemystay.ai",
    ]
else:
    allowed_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://makemystay.ai",
        "https://www.makemystay.ai",
        "https://admin.makemystay.ai",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def csrf_protect(request: Request, call_next):
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        # Bearer-token auth is not vulnerable to CSRF — browsers never attach
        # Authorization headers automatically, so skip the check entirely.
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return await call_next(request)

        exempt_prefixes = [
            "/api/v1/auth/",
            "/api/v1/payments/",
            "/api/v1/payment/",
            "/payments/",
            "/api/v1/realty/contacts",
            "/api/v1/housing/",
            "/api/v1/webhooks/",
            "/api/v1/whatsapp/",
            "/api/v1/meta-whatsapp/",
            "/api/v1/demo/",
        ]
        path = request.url.path
        if any(path.startswith(p) for p in exempt_prefixes):
            return await call_next(request)

        cookie_csrf = request.cookies.get("csrf_token")
        header_csrf = request.headers.get(
            "x-csrf-token", request.headers.get("X-CSRF-Token")
        )
        if not cookie_csrf or not header_csrf or cookie_csrf != header_csrf:
            return JSONResponse(
                status_code=403, content={"detail": "CSRF verification failed"}
            )
    return await call_next(request)

# --- Database initialization (optional create_all; Alembic is source of truth in prod) ---
from app.bootstrap.database import maybe_create_tables_from_metadata  # noqa: E402

maybe_create_tables_from_metadata()


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    path = request.url.path
    if path in THROTTLED_ERROR_ENDPOINTS:
        if should_log_once(f"error:{path}", window_seconds=60):
            logger.error(f"Unhandled exception at {path}: {exc}")
    else:
        logger.error(f"Unhandled exception at {path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": str(exc),
        },
    )


@app.get("/health", tags=["Health"])
async def health():
    """Detailed health check endpoint."""
    from app.configs.db_config import mysql_engine
    try:
        # Check DB
        from sqlalchemy import text
        with mysql_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "service": "Realty API",
        "version": "1.0.0",
        "env": settings.ENV,
        "database": db_status,
        "scheduler": "running" if scheduler.running else "stopped"
    }

# --- Routers (see app/bootstrap/routers.py) ---
from app.bootstrap.routers import register_routers  # noqa: E402

register_routers(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
