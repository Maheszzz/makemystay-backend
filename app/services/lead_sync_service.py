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
import time
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.log_dedupe import should_log_once
from app.configs.db_config import MySQLSessionLocal
from app.models.sync_metadata import SyncMetadata
from app.schemas.lead import LeadCreate
from app.services.housing_lead_service import (
    BROKER_API_URL,
    BUILDER_API_URL,
    housing_lead_service,
)
from app.services.lead_processor import process_lead


# ---------------------------------------------------------------------------
# Public entry point (called by APScheduler every N seconds)
# ---------------------------------------------------------------------------

async def sync_all_sources():
    """Run all lead-source syncs; each in its own DB session and error bubble."""
    results = await asyncio.gather(
        _run_housing_sync(),
        _run_99acres_sync(),
        return_exceptions=True,          # never let one source cancel another
    )
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"sync_all_sources: a source sync raised: {r}")

async def sync_daily_recovery():
    """Daily safety sync that force-pulls the latest 24-hour window."""
    results = await asyncio.gather(
        _run_housing_sync(forced_lookback_seconds=86400),
        _run_99acres_sync(),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"sync_daily_recovery: a source sync raised: {r}")


# ---------------------------------------------------------------------------
# Housing.com sync (builder + broker)
# ---------------------------------------------------------------------------

async def _run_housing_sync(forced_lookback_seconds: Optional[int] = None):
    """Top-level wrapper: creates its own DB session, never leaks exceptions."""
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
# 99acres sync (webhook-primary; pull stub for future use)
# ---------------------------------------------------------------------------

async def _run_99acres_sync():
    db = MySQLSessionLocal()
    try:
        await sync_99acres_leads(db)
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
    finally:
        db.close()


async def sync_99acres_leads(db: Session):
    """99acres primarily pushes leads via webhooks; pull API not yet active."""
    logger.debug("99acres pull-based sync skipped — no active pull API configured")
    await asyncio.sleep(0)
