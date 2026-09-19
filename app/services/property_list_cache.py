"""Redis cache for GET /realty/properties (short TTL, version-bumped on writes)."""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional

from app.core.redis import redis_conn
from app.services.frontend_revalidate import revalidate_frontend_cache_sync

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


def bump_properties_list_cache(property_id: Optional[int] = None, slug: Optional[str] = None) -> None:
    """Invalidate logical list cache (new version makes old keys unreachable) and trigger Next.js revalidate webhook."""
    if redis_conn:
        try:
            redis_conn.incr(CACHE_VERSION_KEY)
        except Exception:
            pass
            
    tags = ["properties-list", "properties"]
    if property_id:
        tags.append(f"property-{property_id}")
    if slug:
        tags.append(f"property-{slug}")
        
    revalidate_frontend_cache_sync(tags)


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
