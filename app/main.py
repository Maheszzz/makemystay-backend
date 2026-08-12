"""FastAPI application for Realty API."""

import logging
from contextlib import asynccontextmanager

try:
    import sentry_sdk
except ImportError:
    sentry_sdk = None  # type: ignore[assignment, misc]

from dotenv import load_dotenv
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import GZipMiddleware
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import json
import time
import socket
from collections import defaultdict
from time import perf_counter

from app.core.config import settings
from app.core.log_dedupe import should_log_once
from app.configs.db_config import get_mysql_db
from app.utils.performance import (
    PRIVATE_NO_STORE,
    PUBLIC_CRAWLER_CACHE,
    PUBLIC_SHORT_CACHE,
    apply_security_and_timing_headers,
)

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
from app.services.s3_orphan_cleanup import run_s3_uploads_orphan_cleanup

scheduler = BackgroundScheduler()
THROTTLED_ERROR_ENDPOINTS = {"/api/v1/admin/analytics", "/api/v1/realty/properties"}

# --- Sentry Setup ---
if settings.SENTRY_DSN:
    if sentry_sdk is None:
        logger.warning(
            "SENTRY_DSN is set but sentry_sdk is not installed; "
            "run `pip install sentry-sdk` using this environment's Python. Sentry disabled."
        )
    else:
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


def s3_orphan_cleanup_job():
    """Remove unreferenced objects under uploads/ (feature-flagged)."""
    run_s3_uploads_orphan_cleanup()

# --- Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the app."""
    logger.info("Starting background scheduler...")
    
    # Run DB init only when enabled (avoids hanging top-level imports)
    try:
        maybe_create_tables_from_metadata()
    except Exception as e:
        logger.error(f"Database initialization helper failed: {e}")

    # Housing / 99acres pull sync requires MySQL; disable when DB is unavailable locally (see LEAD_PULL_SYNC_ENABLED).
    if getattr(settings, "RUN_SCHEDULER", False) and getattr(settings, "LEAD_PULL_SYNC_ENABLED", False):
        scheduler.add_job(
            sync_all_job,
            "interval",
            seconds=settings.HOUSING_SYNC_INTERVAL_SECONDS,
            id="sync_all_job",
            next_run_time=datetime.now(),
        )
    else:
        logger.warning(
            "LEAD_PULL_SYNC_ENABLED=false or RUN_SCHEDULER=false — sync not scheduled."
        )
    if getattr(settings, "RUN_SCHEDULER", False) and settings.LEAD_DAILY_SYNC_ENABLED and getattr(settings, "LEAD_PULL_SYNC_ENABLED", False):
        scheduler.add_job(
            daily_recovery_sync_job,
            "cron",
            hour=settings.LEAD_DAILY_SYNC_HOUR_UTC,
            minute=settings.LEAD_DAILY_SYNC_MINUTE_UTC,
            id="daily_recovery_sync_job",
        )

    if getattr(settings, "RUN_SCHEDULER", False) and getattr(settings, "EMAIL_POLL_INTERVAL_MINUTES", 0) > 0:
        scheduler.add_job(
            email_sync_wrapper_job,
            "interval",
            minutes=settings.EMAIL_POLL_INTERVAL_MINUTES,
            id="email_sync_job",
            next_run_time=datetime.now(),
        )

    if getattr(settings, "RUN_SCHEDULER", False) and getattr(settings, "S3_ORPHAN_CLEANUP_ENABLED", False):
        scheduler.add_job(
            s3_orphan_cleanup_job,
            "cron",
            hour=settings.S3_ORPHAN_CLEANUP_CRON_HOUR_UTC,
            minute=settings.S3_ORPHAN_CLEANUP_CRON_MINUTE_UTC,
            id="s3_orphan_cleanup_job",
        )

    if getattr(settings, "RUN_SCHEDULER", False):
        scheduler.start()
    else:
        logger.info("Background scheduler disabled for this instance (RUN_SCHEDULER=false)")
    if getattr(settings, "LEAD_PULL_SYNC_ENABLED", False):
        logger.info(
            f"APScheduler: sync_all_job every {settings.HOUSING_SYNC_INTERVAL_SECONDS}s"
        )
    if settings.LEAD_DAILY_SYNC_ENABLED and getattr(settings, "LEAD_PULL_SYNC_ENABLED", False):
        logger.info(
            "Daily recovery sync enabled at "
            f"{settings.LEAD_DAILY_SYNC_HOUR_UTC:02d}:{settings.LEAD_DAILY_SYNC_MINUTE_UTC:02d} UTC"
        )
    if getattr(settings, "EMAIL_POLL_INTERVAL_MINUTES", 0) > 0:
        logger.info(f"Email sync job scheduled every {settings.EMAIL_POLL_INTERVAL_MINUTES}m")
    if getattr(settings, "S3_ORPHAN_CLEANUP_ENABLED", False):
        logger.info(
            "S3 orphan cleanup (uploads/) scheduled daily at "
            f"{settings.S3_ORPHAN_CLEANUP_CRON_HOUR_UTC:02d}:{settings.S3_ORPHAN_CLEANUP_CRON_MINUTE_UTC:02d} UTC "
            f"(dry_run={settings.S3_ORPHAN_CLEANUP_DRY_RUN})"
        )
    yield
    logger.info("Shutting down background scheduler...")
    if scheduler.running:
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
PUBLIC_CACHEABLE_PREFIXES = (
    "/api/v1/seo/",
)
PUBLIC_CRAWLER_FILES = (
    "/robots.txt",
    "/sitemap.xml",
    "/sitemap-properties.xml",
    "/sitemap-cities.xml",
    "/sitemap-locations.xml",
    "/sitemap-blog.xml",
    "/sitemap-static.xml",
)


@app.middleware("http")
async def performance_headers_middleware(request: Request, call_next):
    started_at = perf_counter()
    response = await call_next(request)
    apply_security_and_timing_headers(response, started_at)

    path = request.url.path
    method = request.method.upper()
    if method in {"GET", "HEAD"}:
        if path in PUBLIC_CRAWLER_FILES:
            response.headers.setdefault("Cache-Control", PUBLIC_CRAWLER_CACHE)
            response.headers.setdefault("Vary", "Accept-Encoding")
        elif path.startswith(PUBLIC_CACHEABLE_PREFIXES):
            response.headers.setdefault("Cache-Control", PUBLIC_SHORT_CACHE)
            response.headers.setdefault("Vary", "Accept-Encoding")
    elif path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", PRIVATE_NO_STORE)

    return response


@app.middleware("http")
async def log_request_headers(request: Request, call_next):
    if "/uploads/binary" in request.url.path:
        auth = request.headers.get("authorization", "MISSING")
        logger.info(f"UPLOAD REQ | path={request.url.path} auth={auth[:20]}... | type={request.headers.get('content-type')}")
    return await call_next(request)

# CSRF first, then CORS (last add_middleware = outermost in Starlette) so OPTIONS preflights
# hit CORSMiddleware before any other logic. See Starlette `reversed(user_middleware)` stack build.
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
            "/api/v1/schedule-demo",
            "/api/v1/public",
            "/api/v1/properties",
            "/api/v1/enterprise/properties",
            "/api/v1/documents",
            "/api/v1/upload",
            "/api/v1/uploads",
            "/api/v1/leads/widget",
        ]
        path = request.url.path
        if any(path.startswith(p) for p in exempt_prefixes):
            return await call_next(request)

        # Anonymous public writes (no login → no double-submit CSRF cookie), same as /realty/contacts.
        if "/realty/properties/" in path and path.rstrip("/").endswith("/reviews"):
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

# CORS — registered after CSRF so CORS wraps the app outermost (handles OPTIONS immediately).
# Starlette returns 400 on OPTIONS preflight when Origin is not allowed ("Disallowed CORS origin").
# ENV defaults to production in Settings — local admin (localhost / 127.0.0.1, any port) must still work.
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
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "https://makemystay.ai",
        "https://www.makemystay.ai",
        "https://admin.makemystay.ai",
    ]

_extra = (getattr(settings, "CORS_EXTRA_ORIGINS", None) or "").strip()
if _extra:
    allowed_origins = list(allowed_origins) + [o.strip() for o in _extra.split(",") if o.strip()]

_LOCAL_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=_LOCAL_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# --- Database initialization (Alembic is source of truth in prod; dev-only helper moved to lifespan) ---
from app.bootstrap.database import maybe_create_tables_from_metadata  # noqa: E402


@app.middleware("http")
async def standardize_response_middleware(request: Request, call_next):
    """Standardizes JSON responses into {success, data, error} format."""
    # Skip for health checks, metrics, and documentation
    # Nginx proxies /api/* with full path; ALB often checks /api/v1/live (not /live).
    p = request.url.path
    if p in (
        "/health",
        "/live",
        "/api/v1/health",
        "/api/v1/live",
        "/metrics",
        "/robots.txt",
        "/sitemap.xml",
        "/sitemap-properties.xml",
        "/sitemap-cities.xml",
        "/sitemap-locations.xml",
        "/sitemap-blog.xml",
        "/sitemap-static.xml",
    ) or p.startswith("/docs") or p.startswith("/openapi") or p.startswith("/api/v1/internal"):
        return await call_next(request)

    response = await call_next(request)

    # 1. Skip if not JSON or already specialized response (like StreamingResponse)
    # We only wrap standard JSONResponse objects to avoid 'Exit code 18' (Connection Reset)
    # which happens when consuming streaming response bodies incorrectly.
    content_type = response.headers.get("Content-Type", "")
    content_length = int(response.headers.get("Content-Length", 0))
    
    if "application/json" not in content_type or not isinstance(response, JSONResponse):
        return response

    # 2. Skip if already standardized or payload is too large (> 1MB)
    if response.headers.get("X-Standardized") == "true" or content_length > 1_000_000:
        return response

    try:
        # 3. Safe to read .body for standard JSONResponse
        # Check content_length to avoid huge JSON parse
        if content_length > 500_000: # 500KB limit for wrapping
            return response

        body_content = response.body.decode("utf-8")
        if not body_content:
            return response
        data = json.loads(body_content)

        # 3. Check if it already matches the contract (success field present)
        # Some routes might manually return the standardized format
        if isinstance(data, dict) and "success" in data and "data" in data:
            return response

        # 4. Wrap the data
        wrapped = {
            "success": True,
            "data": data,
            "error": None
        }
        
        # 5. Create new response while preserving original status and headers
        standardized_res = JSONResponse(content=wrapped, status_code=response.status_code)
        for k, v in response.headers.items():
            if k.lower() not in ["content-length", "content-type"]:
                standardized_res.headers[k] = v
        
        standardized_res.headers["X-Standardized"] = "true"
        return standardized_res

    except (json.JSONDecodeError, Exception):
        # Fallback to original response for any issues
        return response

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
        status_code=200, # Use 200 to keep UI stable
        content={
            "success": False,
            "data": None,
            "error": str(exc) if settings.ENV != "production" else "A server error occurred. Please try again later.",
        },
    )


@app.get("/", tags=["Health"])
def root():
    """Root endpoint for status check."""
    return {"message": "Makemystay API is live 🚀"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Favicon placeholder."""
    return {}


@app.get("/api/v1/live", tags=["Health"])
@app.get("/live", tags=["Health"])
async def live():
    """Liveness check for ALB."""
    return {"status": "ok", "message": "API is alive"}


@app.get("/api/v1/health", tags=["Health"])
@app.get("/health", tags=["Health"])
async def health():
    """Detailed health check endpoint."""
    from app.configs.db_config import mysql_engine
    from app.core.redis import redis_conn
    
    # Check DB
    try:
        from sqlalchemy import text
        with mysql_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.warning(f"Health check DB failure: {e}")
        db_status = "disconnected"

    # Check Redis
    try:
        if redis_conn:
            redis_conn.ping()
            redis_status = "connected"
        else:
            redis_status = "not_configured"
    except Exception as e:
        logger.warning(f"Health check Redis failure: {e}")
        redis_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" and redis_status == "connected" else "degraded",
        "service": "Realty API",
        "version": "1.0.0",
        "env": settings.ENV,
        "database": db_status,
        "redis": redis_status,
        "scheduler": "running" if scheduler.running else "stopped"
    }


@app.get("/api/v1/whoami", tags=["Health"])
def whoami():
    """Debug endpoint to identify the instance."""
    return {
        "hostname": socket.gethostname(),
        "env": settings.ENV,
        "ip": socket.gethostbyname(socket.gethostname())
    }


# --- Routers (see app/bootstrap/routers.py) ---
from app.bootstrap.routers import register_routers  # noqa: E402

register_routers(app)


if __name__ == "__main__":
    import os

    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
