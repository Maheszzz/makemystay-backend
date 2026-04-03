"""Delete orphaned objects under uploads/ not referenced by property_images."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import func

from app.configs.db_config import MySQLSessionLocal
from app.core.config import settings
from app.models.realty import PropertyImage
from app.utils.property_image_mime import extract_s3_object_key_from_public_url
from app.utils.s3_client import get_s3_client
from app.services.upload_alerts import emit_upload_event, increment_upload_counter

UPLOADS_PREFIX = "uploads/"


def _referenced_image_keys(db) -> set[str]:
    keys: set[str] = set()
    rows = (
        db.query(PropertyImage.image_url)
        .filter(func.coalesce(PropertyImage.is_deleted, False) == False)  # noqa: E712
        .all()
    )
    for (url,) in rows:
        if not url:
            continue
        k = extract_s3_object_key_from_public_url(url)
        if k:
            keys.add(k)
    return keys


def run_s3_uploads_orphan_cleanup() -> dict:
    """
    List objects under uploads/, delete those not referenced in DB and older than min age.
    Respects S3_ORPHAN_CLEANUP_DRY_RUN (log only).
    """
    stats: dict = {
        "scanned": 0,
        "candidates": 0,
        "deleted": 0,
        "dry_run": settings.S3_ORPHAN_CLEANUP_DRY_RUN,
        "skipped_disabled": False,
    }
    if not settings.S3_ORPHAN_CLEANUP_ENABLED:
        stats["skipped_disabled"] = True
        return stats

    client = get_s3_client()
    bucket = settings.S3_BUCKET_NAME
    if not client or not bucket:
        logger.warning("s3_orphan_cleanup: missing S3 client or S3_BUCKET_NAME")
        return stats

    min_age = timedelta(
        hours=settings.S3_ORPHAN_CLEANUP_MIN_AGE_HOURS,
        minutes=settings.S3_ORPHAN_CLEANUP_MIN_AGE_MINUTES,
    )
    now = datetime.now(timezone.utc)
    max_del = settings.S3_ORPHAN_CLEANUP_MAX_DELETES_PER_RUN
    deleted = 0
    alert_thr = getattr(settings, "S3_ORPHAN_CLEANUP_ALERT_DELETES_THRESHOLD", 0) or 0

    db0 = MySQLSessionLocal()
    try:
        ref_snapshot = _referenced_image_keys(db0)
    finally:
        db0.close()

    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=UPLOADS_PREFIX):
        for obj in page.get("Contents") or []:
            stats["scanned"] += 1
            key = obj["Key"]
            lm = obj["LastModified"]
            if lm.tzinfo is None:
                lm = lm.replace(tzinfo=timezone.utc)
            if now - lm < min_age:
                continue
            if key in ref_snapshot:
                continue
            stats["candidates"] += 1
            if deleted >= max_del:
                logger.warning(
                    "s3_orphan_cleanup: max deletes per run ({}) reached",
                    max_del,
                )
                stats["deleted"] = deleted
                return stats
            if settings.S3_ORPHAN_CLEANUP_DRY_RUN:
                logger.info("s3_orphan_cleanup dry_run would delete key={!r}", key)
            else:
                db2 = MySQLSessionLocal()
                try:
                    ref2 = _referenced_image_keys(db2)
                finally:
                    db2.close()
                if key in ref2:
                    logger.info(
                        "s3_orphan_cleanup skip delete key={!r} (referenced since listing)",
                        key,
                    )
                    continue
                try:
                    client.delete_object(Bucket=bucket, Key=key)
                    deleted += 1
                    if alert_thr > 0 and deleted == alert_thr:
                        emit_upload_event(
                            "s3_orphan_cleanup_delete_threshold",
                            deleted=deleted,
                            threshold=alert_thr,
                        )
                except Exception as e:
                    logger.error("s3_orphan_cleanup delete failed key={!r}: {}", key, e)

    stats["deleted"] = deleted if not settings.S3_ORPHAN_CLEANUP_DRY_RUN else 0
    if stats["deleted"] and not settings.S3_ORPHAN_CLEANUP_DRY_RUN:
        increment_upload_counter("s3_orphan_cleanup_deleted_batch", stats["deleted"])
    logger.info("s3_orphan_cleanup finished {!r}", stats)
    return stats
