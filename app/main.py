"""FastAPI application for Realty API."""

import logging
import os
import sys

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.auth import router as auth_router
from app.api.realty import realty_router

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)

logging.info("ENV=%s", os.getenv("ENV"))
logging.info("DB_HOST=%s", os.getenv("DB_HOST"))
logging.info("DB_PORT=%s", os.getenv("DB_PORT"))
logging.info("DB_USER=%s", os.getenv("DB_USER"))
logging.info("DB_NAME=%s", os.getenv("DB_NAME"))

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Realty API",
    description="API for managing property listings and contacts",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Configure CORS for frontend connection
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "https://makemystay.ai",
        "https://www.makemystay.ai",
        "https://admin.makemystay.ai",
        "https://api.makemystay.ai",
    ],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create Database Tables
from app.configs.db_config import MySQLBase, mysql_engine

from app.models import sync_metadata  # noqa: F401 — ensure table is registered

MySQLBase.metadata.create_all(bind=mysql_engine)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
        },
    )


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {"status": "healthy", "service": "Realty API"}


@app.get("/health", tags=["Health"])
async def health_check():
    """Detailed health check endpoint."""
    return {"status": "healthy", "service": "Realty API", "version": "1.0.0"}


# Include routers
app.include_router(realty_router, prefix="/api/v1")
app.include_router(auth_router, prefix="/api/v1")
from app.api.upload import router as upload_router

app.include_router(upload_router, prefix="/api/v1")
from app.api.payment import router as payment_router

app.include_router(payment_router, prefix="/api/v1")
from app.api.demo import router as demo_router

app.include_router(demo_router, prefix="/api/v1")
from app.api.retell import retell_router

app.include_router(retell_router, prefix="/api/v1")
from app.api.housing import housing_router
app.include_router(housing_router, prefix="/api/v1")

# Include webhooks at both /api/v1 and root for maximum reachability
from app.api.webhooks import webhooks_router
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(webhooks_router)


# ------------------------------------------------------------------ #
#  Background cron: Housing.com lead auto-sync (every 2 min)
# ------------------------------------------------------------------ #
import asyncio

from app.cron.fetch_housing_leads import housing_cron_loop


@app.on_event("startup")
async def start_housing_cron():
    """Launch the Housing.com lead sync cron on app startup."""
    asyncio.create_task(housing_cron_loop())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
