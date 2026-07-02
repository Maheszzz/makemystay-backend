from __future__ import annotations

import hashlib
from time import perf_counter
from typing import Optional

from starlette.responses import Response


PUBLIC_SHORT_CACHE = "public, max-age=300, stale-while-revalidate=3600"
PUBLIC_CRAWLER_CACHE = "public, max-age=3600, stale-while-revalidate=86400"
PRIVATE_NO_STORE = "no-store"


def weak_etag(content: str | bytes) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return f'W/"{hashlib.sha256(data).hexdigest()[:24]}"'


def set_public_cache_headers(
    response: Response,
    *,
    cache_control: str = PUBLIC_SHORT_CACHE,
    etag: Optional[str] = None,
) -> Response:
    response.headers.setdefault("Cache-Control", cache_control)
    response.headers.setdefault("Vary", "Accept-Encoding")
    if etag:
        response.headers.setdefault("ETag", etag)
    return response


def apply_security_and_timing_headers(response: Response, started_at: float) -> None:
    duration_ms = max((perf_counter() - started_at) * 1000, 0)
    response.headers.setdefault("X-Response-Time", f"{duration_ms:.2f}ms")
    response.headers.setdefault("Server-Timing", f"app;dur={duration_ms:.2f}")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(self), payment=()",
    )
