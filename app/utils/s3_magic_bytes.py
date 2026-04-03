"""Optional libmagic detection from S3 object bytes (Range GET)."""

from __future__ import annotations

from typing import Optional

from loguru import logger

from app.utils.property_image_mime import ALLOWED_IMAGE_MIME_TYPES, normalize_content_type_for_compare


def detect_image_mime_from_s3_range(
    s3_client,
    bucket: str,
    key: str,
    max_bytes: int = 8192,
) -> Optional[str]:
    """
    Read first max_bytes via Range GET and run libmagic. Returns normalized image/* or None.
    Requires `python-magic` and OS libmagic; returns None if unavailable or on error.
    """
    try:
        import magic  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("python-magic not installed; skipping byte MIME detection")
        return None

    rng = f"bytes=0-{max(0, max_bytes - 1)}"
    try:
        resp = s3_client.get_object(Bucket=bucket, Key=key, Range=rng)
        body = resp["Body"].read()
    except Exception as e:
        logger.warning("S3 Range GET for magic failed key={!r}: {}", key, e)
        return None

    if not body:
        return None

    try:
        raw = magic.from_buffer(body, mime=True)
    except Exception as e:
        logger.warning("magic.from_buffer failed key={!r}: {}", key, e)
        return None

    mt = normalize_content_type_for_compare(raw) or ""
    if mt == "image/jpg":
        mt = "image/jpeg"
    if mt in ALLOWED_IMAGE_MIME_TYPES:
        return mt
    return None
