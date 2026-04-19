"""Redis cache for GET /realty/properties (short TTL, version-bumped on writes)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional

from app.core.redis import redis_conn

CACHE_VERSION_KEY = "cache:realty:properties:list:ver"
KEY_PREFIX = "cache:realty:properties:list"
DEFAULT_TTL_SECONDS = 300  # 5 minutes


def _cache_version() -> str:
    if not redis_conn:
        return "0"
    try:
        v = redis_conn.get(CACHE_VERSION_KEY)
        return v.decode() if v else "0"
    except Exception:
        return "0"


def bump_properties_list_cache() -> None:
    """Invalidate logical list cache (new version makes old keys unreachable)."""
    if redis_conn:
        try:
            redis_conn.incr(CACHE_VERSION_KEY)
        except Exception:
            pass


def properties_list_cache_key(payload: dict[str, Any]) -> str:
    """Stable key from normalized query args."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    h = hashlib.sha256(canonical.encode()).hexdigest()[:40]
    return f"{KEY_PREFIX}:{_cache_version()}:{h}"


def get_cached_properties_list(key: str) -> Optional[Any]:
    if not redis_conn:
        return None
    try:
        raw = redis_conn.get(key)
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None


def set_cached_properties_list(key: str, content: Any, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    if not redis_conn:
        return
    try:
        redis_conn.setex(key, ttl, json.dumps(content, default=str))
    except Exception:
        pass
