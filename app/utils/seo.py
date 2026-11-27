from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import quote


PUBLIC_STATIC_PATHS = (
    "/",
    "/properties",
    "/pg",
    "/rent",
    "/buy",
    "/plots",
    "/contact",
)


def normalize_site_url(site_url: str) -> str:
    value = (site_url or "").strip() or "https://makemystay.ai"
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    return value.rstrip("/")


def canonical_property_type(property_obj: Any) -> str:
    property_type = (getattr(property_obj, "property_type", "") or "").strip().lower()
    listing_type = (getattr(property_obj, "listing_type", "") or "").strip().lower()
    if property_type == "pg":
        return "pg"
    if property_type == "plot":
        return "plot"
    if listing_type in ("buy", "sale"):
        return "buy"
    return "rent"


def safe_slug(value: Optional[str]) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value or "").strip("-").lower()
    return cleaned[:200]


def property_slug(property_obj: Any) -> str:
    existing = safe_slug(getattr(property_obj, "slug", None))
    if existing:
        return existing
    parts = [
        getattr(property_obj, "property_name", None),
        getattr(property_obj, "property_type", None),
        getattr(property_obj, "location", None),
    ]
    return safe_slug("-".join(str(part) for part in parts if part)) or str(getattr(property_obj, "id", ""))


def canonical_property_path(property_obj: Any) -> str:
    return f"/properties/{quote(canonical_property_type(property_obj))}/{quote(property_slug(property_obj))}"


def canonical_property_url(site_url: str, property_obj: Any) -> str:
    return f"{normalize_site_url(site_url)}{canonical_property_path(property_obj)}"


def public_url(site_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{normalize_site_url(site_url)}{normalized_path}"


def truncate_text(value: Optional[str], limit: int) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def money_value(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def primary_image_url(property_obj: Any) -> Optional[str]:
    images = list(getattr(property_obj, "images", None) or [])
    if not images:
        return None
    images.sort(
        key=lambda img: (
            not bool(getattr(img, "is_primary", False)),
            getattr(img, "sort_order", 0) or 0,
            getattr(img, "id", 0) or 0,
        )
    )
    return getattr(images[0], "image_url", None)


def xml_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date().isoformat()
    return datetime.now(timezone.utc).date().isoformat()
