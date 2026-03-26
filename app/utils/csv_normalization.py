"""Normalize CSV-derived strings before LeadCreate (consistent data across portal formats)."""

from __future__ import annotations

from typing import Optional

from app.utils.phone_normalize import normalize_to_indian_mobile_10


def normalize_phone(raw: str) -> Optional[str]:
    """Indian 10-digit mobile for leads; delegates to shared phone helper."""
    return normalize_to_indian_mobile_10(raw)


def normalize_name(raw: str, *, default: str = "User", max_len: int = 200) -> str:
    if not raw or not str(raw).strip():
        return default
    t = " ".join(str(raw).strip().split())
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    return t


def normalize_location(raw: Optional[str], *, max_len: int = 500) -> Optional[str]:
    if raw is None:
        return None
    t = " ".join(str(raw).strip().split())
    if not t:
        return None
    if len(t) > max_len:
        t = t[:max_len].rstrip()
    return t
