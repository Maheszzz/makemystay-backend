"""Unified sync service for all lead sources.

Coordinates fetching leads from pull-based APIs (Housing.com, 99acres, etc.)
and processing them through the centralized lead pipeline.

Crash-proofing guarantees:
- Each source gets its own isolated DB session so one failure can't corrupt another.
- asyncio.gather uses return_exceptions=True so a single-source error never
  silently cancels the others.
- last_lead_timestamp is parsed safely even if stored as a float string.
- Both Housing.com builder AND broker APIs are queried every cycle.
- A 25-hour "safety window" always overlaps the last sync so leads missed
  during short downtime are automatically recovered on the next run.
"""

import asyncio
import threading
import time
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.log_dedupe import should_log_once
from app.configs.db_config import MySQLSessionLocal
from app.models.sync_metadata import SyncMetadata
from app.schemas.lead import LeadCreate
from app.services.alert_service import alert_service
from app.services.housing_lead_service import (
    BROKER_API_URL,
    BUILDER_API_URL,
    housing_lead_service,
)
from app.services.lead_processor import process_lead

# ---------------------------------------------------------------------------
# Scheduler overlap guards
# APScheduler runs syncs via asyncio.run() in a thread-pool thread, so each
# call creates a *new* event loop. threading.Lock is the correct primitive
# here — asyncio.Lock would not transfer across event loops.
# ---------------------------------------------------------------------------
_housing_sync_lock = threading.Lock()
_99acres_sync_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Public entry point (called by APScheduler every N seconds)
# ---------------------------------------------------------------------------

async def sync_all_sources():
    """Run all lead-source syncs; each in its own DB session and error bubble.
    Uses a Redis distributed lock to ensure only one worker process runs this at a time.
    """
    from app.core.redis import redis_conn
    
    lock_key = "lock:global_lead_sync"
    is_locked = False
    
    if redis_conn:
        # Acquire lock with 5-minute expiry to prevent deadlocks on crash
        is_locked = redis_conn.set(lock_key, "locked", nx=True, ex=300)
        if not is_locked:
            logger.debug("Global lead sync skipped: another worker process is already running it")
            return

    try:
        results = await asyncio.gather(
            _run_housing_sync(),
            _run_99acres_sync(),
            return_exceptions=True,          # never let one source cancel another
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"sync_all_sources: a source sync raised: {r}")
                # Proactive alerting for production
                if settings.ENV == "production":
                    await alert_service.send_alert(
                        f"Lead sync failed for a source: {r}\nCheck PM2 logs for details.",
                        level="error"
                    )
    finally:
        if is_locked and redis_conn:
            redis_conn.delete(lock_key)

async def sync_daily_recovery():
    """Daily safety sync that force-pulls the latest 24-hour window.
    Also uses a Redis lock to avoid redundant recovery runs.
    """
    from app.core.redis import redis_conn
    
    lock_key = "lock:daily_recovery_sync"
    is_locked = False
    
    if redis_conn:
        is_locked = redis_conn.set(lock_key, "locked", nx=True, ex=3600) # 1 hour lock for daily
        if not is_locked:
            logger.debug("Daily recovery sync skipped: another worker is already running it")
            return

    try:
        results = await asyncio.gather(
            _run_housing_sync(forced_lookback_seconds=86400),
            _run_99acres_sync(forced_lookback_seconds=86400),
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, Exception):
                logger.error(f"sync_daily_recovery: a source sync raised: {r}")
                if settings.ENV == "production":
                    await alert_service.send_alert(
                        f"Daily lead recovery failed: {r}",
                        level="warning"
                    )
    finally:
        if is_locked and redis_conn:
            redis_conn.delete(lock_key)


# ---------------------------------------------------------------------------
# Housing.com sync (builder + broker)
# ---------------------------------------------------------------------------

async def _run_housing_sync(forced_lookback_seconds: Optional[int] = None):
    """Top-level wrapper: creates its own DB session, never leaks exceptions.

    Uses a threading lock to skip if a previous run hasn't finished yet
    (prevents stacking when the API is slow and the interval fires again).
    """
    if not _housing_sync_lock.acquire(blocking=False):
        logger.warning("Housing sync skipped — previous run still in progress")
        return
    db = MySQLSessionLocal()
    try:
        await sync_housing_leads(db, forced_lookback_seconds=forced_lookback_seconds)
    except OperationalError as e:
        try:
            db.rollback()
        except Exception:
            pass
        # MySQL down / wrong host: expected in local dev; avoid ERROR every 30s.
        if should_log_once("housing_sync_mysql_unreachable", 300):
            logger.warning(
                "Housing lead sync skipped: cannot connect to MySQL. "
                "Start the DB, fix DB_HOST/DB_PORT in .env, or set LEAD_PULL_SYNC_ENABLED=false. "
                f"({e})"
            )
    except Exception as e:
        logger.error(f"Housing sync wrapper caught unhandled error: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
        _housing_sync_lock.release()


async def sync_housing_leads(db: Session, forced_lookback_seconds: Optional[int] = None):
    """Fetch and store leads from Housing.com (builder + broker endpoints)."""
    if not housing_lead_service.is_configured:
        logger.debug("Housing.com sync skipped — not configured")
        return

    # ── 1. Load / create sync metadata ──────────────────────────────────────
    meta = db.query(SyncMetadata).filter(SyncMetadata.source == "housing").first()
    if not meta:
        meta = SyncMetadata(source="housing")
        db.add(meta)
        db.commit()
        db.refresh(meta)

    now = int(time.time())

    if forced_lookback_seconds is not None and forced_lookback_seconds > 0:
        # Explicit daily recovery mode: always fetch a full recent window.
        start_int = now - forced_lookback_seconds
    else:
        # Safe float-string parsing: "1742400000.0" would crash int("1742400000.0")
        if meta.last_lead_timestamp:
            try:
                start_int = int(float(str(meta.last_lead_timestamp)))
            except (ValueError, TypeError):
                logger.warning("Corrupt last_lead_timestamp — defaulting to 24h ago")
                start_int = now - 86400
        else:
            start_int = now - 86400   # first run: look back 24 h

        # Always overlap the last 25 h so short-downtime gaps are self-healing.
        # Example: server was down for 1 h → overlap re-fetches that window next cycle.
        overlap_start = now - 90000  # 25 h ago
        start_int = min(start_int, overlap_start)

    # Housing API hard limit: ≤ 48 h per request (our service chunks automatically,
    # but cap the total window at 47 h so one slow sync doesn't snowball).
    end_int = now
    if end_int - start_int > 170000:      # 170 000 s ≈ 47 h
        end_int = start_int + 170000

    start_date = str(start_int)
    end_date   = str(end_int)

    logger.info(
        f"Housing sync window: {datetime.fromtimestamp(start_int).isoformat()} → "
        f"{datetime.fromtimestamp(end_int).isoformat()}"
    )

    # ── 2. Fetch from both builder AND broker endpoints ──────────────────────
    builder_leads, broker_leads = await asyncio.gather(
        housing_lead_service.fetch_leads(start_date, end_date, api_url=BUILDER_API_URL),
        housing_lead_service.fetch_leads(start_date, end_date, api_url=BROKER_API_URL),
        return_exceptions=True,
    )

    all_raw: list = []

    for label, result in [("builder", builder_leads), ("broker", broker_leads)]:
        if isinstance(result, Exception):
            logger.error(f"Housing {label} fetch raised: {result}")
            continue
        leads, error = result
        if error:
            logger.error(f"Housing {label} API error: {error}")
            continue
        logger.info(f"Housing {label}: {len(leads)} leads fetched")
        all_raw.extend(leads)

    if not all_raw:
        logger.info("Housing sync: no leads returned from either endpoint")
        _update_meta(db, meta, end_date, fetched=0, imported=0, skipped=0)
        return

    # ── 3. Process each lead through the pipeline ────────────────────────────
    imported = 0
    skipped  = 0

    for raw_lead in all_raw:
        mapped = housing_lead_service.map_lead(raw_lead)
        phone  = (mapped.get("phone") or "").strip()

        if len(phone) < 7:
            logger.warning(f"Housing lead skipped — short phone: {phone!r}")
            skipped += 1
            continue

        try:
            lead_data = LeadCreate(
                name          = mapped.get("name"),
                phone         = phone,
                email         = mapped.get("email"),
                project_name  = mapped.get("project_name"),
                location      = mapped.get("location"),
                property_type = mapped.get("property_type"),
                budget        = mapped.get("budget"),
                message       = mapped.get("message"),
                lead_date     = mapped.get("lead_date"),
                external_id   = mapped.get("external_id"),
            )
        except Exception as val_err:
            logger.warning(f"Housing lead validation error (phone={phone!r}): {val_err}")
            skipped += 1
            continue

        result = await process_lead(db, lead_data, source="housing", raw_payload=raw_lead)
        if result:
            imported += 1
        else:
            skipped += 1

    _update_meta(db, meta, end_date, fetched=len(all_raw), imported=imported, skipped=skipped)
    logger.success(
        f"Housing sync done: {len(all_raw)} fetched, {imported} imported, {skipped} skipped"
    )


def _update_meta(
    db: Session,
    meta: SyncMetadata,
    end_date: str,
    *,
    fetched: int,
    imported: int,
    skipped: int,
):
    """Persist sync metadata; rolls back safely on failure."""
    try:
        meta.last_lead_timestamp = end_date
        meta.last_sync_at        = datetime.now()
        meta.leads_fetched       = fetched
        meta.leads_imported      = imported
        meta.status              = "active"
        meta.last_error          = None
        db.commit()
    except Exception as e:
        logger.error(f"Failed to update sync metadata: {e}")
        db.rollback()


# ---------------------------------------------------------------------------
# 99acres sync — pull-based (webhook-push is primary; pull is safety fallback)
# Requires ACRES_API_KEY from 99acres account manager to activate pull.
# ---------------------------------------------------------------------------

async def _run_99acres_sync(forced_lookback_seconds: Optional[int] = None):
    """Top-level wrapper: creates its own DB session, never leaks exceptions.

    Uses a threading lock to skip if a previous run hasn't finished yet
    (prevents stacking when the API is slow and the interval fires again).
    """
    if not _99acres_sync_lock.acquire(blocking=False):
        logger.warning("99acres sync skipped — previous run still in progress")
        return
    db = MySQLSessionLocal()
    try:
        await sync_99acres_leads(db, forced_lookback_seconds=forced_lookback_seconds)
    except OperationalError as e:
        try:
            db.rollback()
        except Exception:
            pass
        if should_log_once("99acres_sync_mysql_unreachable", 300):
            logger.warning(
                "99acres sync skipped: cannot connect to MySQL. ({})",
                e,
            )
    except Exception as e:
        logger.error(f"99acres sync wrapper caught: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
        _99acres_sync_lock.release()


async def sync_99acres_leads(
    db: Session,
    forced_lookback_seconds: Optional[int] = None,
):
    """Fetch and store leads from the 99acres pull API.

    Gracefully skips when ACRES_API_KEY is absent — the push webhook
    (POST /webhooks/99acres) is the primary ingestion path and continues
    to work independently of this pull sync.
    """
    from app.services.acres_lead_service import acres_lead_service

    if not acres_lead_service.is_configured:
        logger.debug(
            "99acres pull sync skipped — ACRES_API_KEY not configured. "
            "Webhook push (/webhooks/99acres) continues as primary ingestion."
        )
        return

    # ── 1. Load / create sync metadata ──────────────────────────────────────
    meta = db.query(SyncMetadata).filter(SyncMetadata.source == "99acres").first()
    if not meta:
        meta = SyncMetadata(source="99acres")
        db.add(meta)
        db.commit()
        db.refresh(meta)

    now = int(time.time())

    if forced_lookback_seconds is not None and forced_lookback_seconds > 0:
        start_int = now - forced_lookback_seconds
    else:
        if meta.last_lead_timestamp:
            try:
                start_int = int(float(str(meta.last_lead_timestamp)))
            except (ValueError, TypeError):
                logger.warning("99acres: corrupt last_lead_timestamp — defaulting to 24h ago")
                start_int = now - 86400
        else:
            start_int = now - 86400  # first run: look back 24 h

        # 25-hour self-healing overlap mirrors Housing.com approach
        overlap_start = now - 90000
        start_int = min(start_int, overlap_start)

    end_int = now
    # Cap at 47 h per cycle; subsequent runs catch up automatically
    if end_int - start_int > 170000:
        end_int = start_int + 170000

    from_date = str(start_int)
    to_date   = str(end_int)

    logger.info(
        f"99acres sync window: {datetime.fromtimestamp(start_int).isoformat()} → "
        f"{datetime.fromtimestamp(end_int).isoformat()}"
    )

    # ── 2. Fetch leads ───────────────────────────────────────────────────────
    leads_raw, error = await acres_lead_service.fetch_leads(from_date, to_date)

    if error:
        logger.error(f"99acres fetch error: {error}")
        meta.status = "error"
        meta.last_error = error
        db.commit()
        return

    logger.info(f"99acres: {len(leads_raw)} leads fetched")

    if not leads_raw:
        logger.info("99acres sync: no leads returned")
        _update_meta(db, meta, to_date, fetched=0, imported=0, skipped=0)
        return

    # ── 3. Deduplicate + process each lead through the pipeline ──────────────
    imported = 0
    skipped  = 0

    for raw_lead in leads_raw:
        mapped = acres_lead_service.map_lead(raw_lead)
        phone  = (mapped.get("phone") or "").strip()

        if len(phone) < 7:
            logger.warning(f"99acres lead skipped — short phone: {phone!r}")
            skipped += 1
            continue

        try:
            lead_data = LeadCreate(
                name          = mapped.get("name"),
                phone         = phone,
                email         = mapped.get("email"),
                city          = mapped.get("city"),
                location      = mapped.get("location"),
                project_name  = mapped.get("project_name"),
                property_type = mapped.get("property_type"),
                budget        = mapped.get("budget"),
                message       = mapped.get("message"),
                lead_date     = mapped.get("lead_date"),
                external_id   = mapped.get("external_id"),
            )
        except Exception as val_err:
            logger.warning(f"99acres lead validation error (phone={phone!r}): {val_err}")
            skipped += 1
            continue

        result = await process_lead(db, lead_data, source="99acres", raw_payload=raw_lead)
        if result:
            imported += 1
        else:
            skipped += 1

    _update_meta(db, meta, to_date, fetched=len(leads_raw), imported=imported, skipped=skipped)
    logger.success(
        f"99acres sync done: {len(leads_raw)} fetched, {imported} imported, {skipped} skipped"
    )
