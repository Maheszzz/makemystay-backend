"""Query helpers for admin payment transaction listing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from app.models.booking import Booking
from app.models.payment import Payment
from app.models.realty import Property

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_GST_RATE = 0.18


def compute_gst_amount(amount: float) -> float:
    """Display GST component assuming amount is GST-inclusive at 18%."""
    if not amount or amount <= 0:
        return 0.0
    return round(float(amount) - (float(amount) / (1 + _GST_RATE)), 2)


def parse_month_range(month: str) -> Tuple[datetime, datetime]:
    """Return UTC [start, end) for YYYY-MM."""
    if not _MONTH_RE.match(month):
        raise ValueError("month must be YYYY-MM")
    year, mon = int(month[:4]), int(month[5:7])
    if mon < 1 or mon > 12:
        raise ValueError("invalid month")
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    if mon == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, mon + 1, 1, tzinfo=timezone.utc)
    return start, end


def parse_datetime_param(value: str) -> datetime:
    raw = value.strip()
    if len(raw) == 10:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def build_payment_transactions_query(
    db: Session,
    *,
    status: Optional[str] = None,
    month: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    property_id: Optional[int] = None,
    city: Optional[str] = None,
    search: Optional[str] = None,
    source_filter: str = "all",
) -> Query:
    """Base query with optional booking/property joins for filters."""
    webhook_exists = None  # set by caller if needed for source

    query = (
        db.query(Payment, Booking, Property)
        .outerjoin(Booking, Payment.order_id == Booking.order_id)
        .outerjoin(Property, Booking.property_id == Property.id)
        .order_by(Payment.created_at.desc())
    )

    if status:
        query = query.filter(Payment.status == status)

    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None
    if month:
        range_start, range_end = parse_month_range(month)
    if date_from:
        range_start = parse_datetime_param(date_from)
    if date_to:
        range_end = parse_datetime_param(date_to)

    if range_start is not None:
        query = query.filter(Payment.created_at >= range_start)
    if range_end is not None:
        query = query.filter(Payment.created_at < range_end)

    if min_amount is not None:
        query = query.filter(Payment.amount >= min_amount)
    if max_amount is not None:
        query = query.filter(Payment.amount <= max_amount)

    if property_id is not None:
        query = query.filter(Booking.property_id == property_id)

    if city:
        query = query.filter(Property.city.ilike(f"%{city.strip()}%"))

    if search:
        q = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Payment.order_id.ilike(q),
                Payment.payment_id.ilike(q),
                Payment.payer_name.ilike(q),
                Payment.payer_email.ilike(q),
                Payment.payer_phone.ilike(q),
            )
        )

    return query


def enrich_transaction_row(
    normalized: dict[str, Any],
    *,
    booking: Optional[Booking],
    property_row: Optional[Property],
) -> dict[str, Any]:
    amount = float(normalized.get("amount") or 0)
    normalized["gst_amount"] = compute_gst_amount(amount)
    if booking and booking.property_id:
        normalized["property_id"] = int(booking.property_id)
    elif property_row:
        normalized["property_id"] = int(property_row.id)
    else:
        normalized["property_id"] = None
    normalized["property_name"] = property_row.property_name if property_row else None
    normalized["property_city"] = property_row.city if property_row else None
    return normalized
