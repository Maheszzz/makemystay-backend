"""Derive and optionally verify image MIME for property_images (trust server-side, not client)."""

from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import unquote, urlparse

from loguru import logger

from app.core.config import settings

# Keep aligned with app.api.upload.ALLOWED_MIME_TYPES
ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

_EXT_TO_MIME = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def derive_image_content_type_from_url(image_url: str) -> str:
    """
    Infer canonical image/* from URL path: mimetypes first, then extension map, then jpeg default.
    """
    try:
        path = unquote(urlparse(image_url).path).lstrip("/")
        if not path:
            return "image/jpeg"
        base = path.rsplit("/", 1)[-1]
        if not base:
            return "image/jpeg"

        guessed, _ = mimetypes.guess_type(base)
        if guessed:
            g = guessed.lower()
            if g == "image/jpg":
                g = "image/jpeg"
            if g in ALLOWED_IMAGE_MIME_TYPES:
                return g

        if "." not in base:
            return "image/jpeg"
        ext = base.rsplit(".", 1)[-1].lower()
        return _EXT_TO_MIME.get(ext, "image/jpeg")
    except Exception as e:
        logger.warning("derive_image_content_type_from_url fallback: {!r} err={}", image_url, e)
        return "image/jpeg"


def normalize_content_type_for_compare(value: str | None) -> str:
    """Strip parameters (e.g. charset) for comparison."""
    if not value:
        return ""
    return value.split(";", 1)[0].strip().lower()


def extract_s3_object_key_from_public_url(image_url: str) -> str | None:
    """
    Return S3 key from our public URLs (virtual-hosted S3 or path-style CloudFront).
    Path after host is the object key.
    """
    try:
        u = urlparse(image_url)
        if u.scheme not in ("http", "https") or not u.netloc:
            return None
        key = unquote(u.path).lstrip("/")
        return key or None
    except Exception:
        return None


@dataclass
class S3HeadVerificationResult:
    ok: bool
    key: str | None
    s3_content_type: str | None
    s3_content_length: int | None
    derived_content_type: str
    mismatch: bool
    error: str | None = None


def verify_s3_object_head(
    *,
    image_url: str,
    derived_content_type: str,
    bucket: str | None,
    s3_client,
    max_attempts: Optional[int] = None,
    retry_base_seconds: Optional[float] = None,
) -> S3HeadVerificationResult:
    """
    HEAD the object (with retries); compare S3 Content-Type to URL-derived MIME.
    Requires IAM s3:GetObject (HeadObject) on the key.
    """
    derived = normalize_content_type_for_compare(derived_content_type) or "image/jpeg"
    if s3_client is None or not bucket:
        return S3HeadVerificationResult(
            ok=False,
            key=None,
            s3_content_type=None,
            s3_content_length=None,
            derived_content_type=derived,
            mismatch=False,
            error="no_s3_client_or_bucket",
        )
    key = extract_s3_object_key_from_public_url(image_url)
    if not key:
        logger.debug("S3 head verify skipped: could not parse key from {!r}", image_url)
        return S3HeadVerificationResult(
            ok=False,
            key=None,
            s3_content_type=None,
            s3_content_length=None,
            derived_content_type=derived,
            mismatch=False,
            error="parse_key_failed",
        )

    attempts = max_attempts if max_attempts is not None else settings.S3_HEAD_MAX_ATTEMPTS
    base = retry_base_seconds if retry_base_seconds is not None else settings.S3_HEAD_RETRY_BASE_SECONDS
    last_err: Optional[Exception] = None
    head = None
    for attempt in range(max(1, attempts)):
        try:
            head = s3_client.head_object(Bucket=bucket, Key=key)
            break
        except Exception as e:
            last_err = e
            logger.warning(
                "S3 head_object attempt {}/{} failed for key={!r}: {}",
                attempt + 1,
                attempts,
                key,
                e,
            )
            if attempt < attempts - 1:
                time.sleep(base * (attempt + 1))

    if head is None:
        return S3HeadVerificationResult(
            ok=False,
            key=key,
            s3_content_type=None,
            s3_content_length=None,
            derived_content_type=derived,
            mismatch=False,
            error=str(last_err) if last_err else "head_failed",
        )

    s3_ct = normalize_content_type_for_compare(head.get("ContentType"))
    length = head.get("ContentLength")
    try:
        s3_len = int(length) if length is not None else None
    except (TypeError, ValueError):
        s3_len = None

    mismatch = bool(s3_ct and derived and s3_ct != derived)
    if mismatch:
        logger.warning(
            "S3 Content-Type mismatch for key={!r}: s3={!r} derived={!r}",
            key,
            s3_ct,
            derived,
        )
    return S3HeadVerificationResult(
        ok=True,
        key=key,
        s3_content_type=s3_ct or None,
        s3_content_length=s3_len,
        derived_content_type=derived,
        mismatch=mismatch,
        error=None,
    )
