"""Admin payment analytics aggregations."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.booking import Booking
from app.models.payment import Payment
from app.models.realty import Property
from app.services.payment_transaction_query import parse_month_range


def _month_bounds(month: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
    if not month:
        return None, None
    return parse_month_range(month)


def payment_analytics_summary(
    db: Session,
    *,
    month: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    from app.models.payment_webhook_event import PaymentWebhookEvent
    from app.models.reconciliation import ReconciliationIssue

    now = now or datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    scoped_start, scoped_end = _month_bounds(month)

    def _success_sum_query():
        q = db.query(func.sum(Payment.amount)).filter(Payment.status == "success")
        if scoped_start is not None:
            q = q.filter(Payment.created_at >= scoped_start, Payment.created_at < scoped_end)
        return q.scalar() or 0

    def _counts_query():
        q = db.query(Payment.status, func.count(Payment.id))
        if scoped_start is not None:
            q = q.filter(Payment.created_at >= scoped_start, Payment.created_at < scoped_end)
        return q.group_by(Payment.status).all()

    success_all = db.query(func.sum(Payment.amount)).filter(Payment.status == "success").scalar() or 0
    success_today = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == "success", Payment.created_at >= today_start)
        .scalar()
        or 0
    )
    success_month = (
        db.query(func.sum(Payment.amount))
        .filter(Payment.status == "success", Payment.created_at >= month_start)
        .scalar()
        or 0
    )
    scoped_revenue = float(_success_sum_query()) if month else float(success_month)

    counts = _counts_query() if month else db.query(Payment.status, func.count(Payment.id)).group_by(Payment.status).all()
    count_dict = {str(status).lower(): count for status, count in counts}

    alert_window_start = now - timedelta(days=14)
    risky_ignored_reasons = {
        "identifiers_missing",
        "payment_creation_failed",
        "event_not_mapped",
    }
    ignored_webhooks = (
        db.query(func.count(PaymentWebhookEvent.id))
        .filter(
            PaymentWebhookEvent.status == "ignored",
            PaymentWebhookEvent.reason.in_(risky_ignored_reasons),
            PaymentWebhookEvent.created_at >= alert_window_start,
            ~PaymentWebhookEvent.event.like("settlement.%"),
            ~PaymentWebhookEvent.event.like("test.%"),
            ~PaymentWebhookEvent.event.like("account.%"),
            ~PaymentWebhookEvent.event.like("route.%"),
            ~PaymentWebhookEvent.event.like("refund.%"),
        )
        .scalar()
        or 0
    )
    failed_webhooks = (
        db.query(func.count(PaymentWebhookEvent.id))
        .filter(
            PaymentWebhookEvent.status == "error",
            PaymentWebhookEvent.created_at >= alert_window_start,
        )
        .scalar()
        or 0
    )
    rejected_inbound_webhooks = (
        db.query(func.count(PaymentWebhookEvent.id))
        .filter(
            PaymentWebhookEvent.status == "rejected",
            PaymentWebhookEvent.created_at >= alert_window_start,
        )
        .scalar()
        or 0
    )
    reconciliation_mismatches = (
        db.query(func.count(ReconciliationIssue.id)).filter(ReconciliationIssue.resolved == False).scalar()
        or 0
    )

    return {
        "revenue_total_all_time": float(success_all),
        "revenue_today": float(success_today),
        "revenue_this_month": float(success_month),
        "revenue_scoped": scoped_revenue,
        "scoped_month": month,
        "payments_breakdown": {
            "success": count_dict.get("success", 0),
            "pending": count_dict.get("pending", 0),
            "failed": count_dict.get("failed", 0),
            "refunded": count_dict.get("refunded", 0),
            "expired": count_dict.get("expired", 0),
        },
        "alerts": {
            "ignored_webhooks": ignored_webhooks,
            "failed_webhooks": failed_webhooks,
            "rejected_inbound_webhooks": rejected_inbound_webhooks,
            "reconciliation_mismatches": reconciliation_mismatches,
        },
    }


def payment_analytics_series(
    db: Session,
    *,
    granularity: str = "daily",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = None,
) -> Dict[str, Any]:
    from app.services.payment_transaction_query import parse_datetime_param

    now = datetime.now(timezone.utc)
    gran = (granularity or "daily").strip().lower()
    if gran not in {"daily", "weekly", "monthly"}:
        raise ValueError("granularity must be daily, weekly, or monthly")

    if month:
        range_start, range_end = parse_month_range(month)
    else:
        range_end = now
        if date_to:
            range_end = parse_datetime_param(date_to)
        if gran == "monthly":
            range_start = range_end - timedelta(days=365)
        elif gran == "weekly":
            range_start = range_end - timedelta(days=84)
        else:
            range_start = range_end - timedelta(days=14)
        if date_from:
            range_start = parse_datetime_param(date_from)

    dialect = db.get_bind().dialect.name
    if gran == "monthly":
        if dialect == "sqlite":
            period_expr = func.strftime("%Y-%m", Payment.created_at)
        else:
            period_expr = func.date_format(Payment.created_at, "%Y-%m")
    elif gran == "weekly":
        if dialect == "sqlite":
            period_expr = func.strftime("%Y-W%W", Payment.created_at)
        else:
            period_expr = func.date_format(Payment.created_at, "%x-W%v")
    else:
        period_expr = func.date(Payment.created_at)

    revenue_rows = (
        db.query(
            period_expr.label("period"),
            func.sum(Payment.amount).label("revenue"),
            func.count(Payment.id).label("count"),
        )
        .filter(
            Payment.status == "success",
            Payment.created_at >= range_start,
            Payment.created_at < range_end,
        )
        .group_by(period_expr)
        .order_by(period_expr)
        .all()
    )

    points = [
        {
            "period": str(row.period),
            "revenue": float(row.revenue or 0),
            "count": int(row.count or 0),
        }
        for row in revenue_rows
    ]

    status_rows = (
        db.query(Payment.status, func.count(Payment.id))
        .filter(Payment.created_at >= range_start, Payment.created_at < range_end)
        .group_by(Payment.status)
        .all()
    )
    status_breakdown = {str(s).lower(): int(c) for s, c in status_rows}
    for key in ("success", "pending", "failed", "refunded", "expired"):
        status_breakdown.setdefault(key, 0)

    top_rows = (
        db.query(
            Property.id.label("property_id"),
            Property.property_name.label("property_name"),
            func.sum(Payment.amount).label("revenue"),
            func.count(Payment.id).label("count"),
        )
        .join(Booking, Payment.order_id == Booking.order_id)
        .join(Property, Booking.property_id == Property.id)
        .filter(
            Payment.status == "success",
            Payment.created_at >= range_start,
            Payment.created_at < range_end,
        )
        .group_by(Property.id, Property.property_name)
        .order_by(func.sum(Payment.amount).desc())
        .limit(5)
        .all()
    )

    top_properties = [
        {
            "property_id": int(row.property_id),
            "property_name": row.property_name,
            "revenue": float(row.revenue or 0),
            "count": int(row.count or 0),
        }
        for row in top_rows
    ]

    return {
        "granularity": gran,
        "from": range_start.isoformat(),
        "to": range_end.isoformat(),
        "points": points,
        "status_breakdown": status_breakdown,
        "top_properties": top_properties,
    }
