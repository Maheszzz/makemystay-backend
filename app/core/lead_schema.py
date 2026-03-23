"""
Single source of truth for lead statuses, priorities, and labels.
Keep in sync with app.models.lead.Lead status Enum column.
"""

from __future__ import annotations

from typing import Any

# Display order for filters / dropdowns (subset of DB enum order doesn't matter for SQL)
LEAD_STATUS_ORDER: tuple[str, ...] = (
    "new",
    "contacted",
    "interested",
    "qualified",
    "followup",
    "not_interested",
    "converted",
    "lost",
)

# Human labels — used when exposing metadata to clients
LEAD_STATUS_LABELS: dict[str, str] = {
    "new": "New",
    "contacted": "Contacted",
    "interested": "Interested",
    "qualified": "Qualified",
    "followup": "Follow-up",
    "not_interested": "Not Interested",
    "converted": "Converted",
    "lost": "Lost",
}

# UI tone hints for admin (maps to Tailwind-style treatment on the client)
LEAD_STATUS_TONES: dict[str, str] = {
    "new": "warning",
    "contacted": "info",
    "qualified": "cyan",
    "followup": "orange",
    "interested": "success",
    "not_interested": "danger",
    "converted": "positive",
    "lost": "muted",
}

VALID_LEAD_STATUSES: frozenset[str] = frozenset(LEAD_STATUS_LABELS.keys())

PRIORITY_LEVELS: tuple[dict[str, Any], ...] = (
    {"value": 1, "label": "Low", "tone": "muted"},
    {"value": 2, "label": "Medium", "tone": "warning"},
    {"value": 3, "label": "High", "tone": "danger"},
)


def lead_status_values_from_model() -> list[str]:
    """Read enum members from the Lead ORM column (matches MySQL enum)."""
    from app.models.lead import Lead

    col = Lead.__table__.c.status
    t = col.type
    if hasattr(t, "enums") and t.enums:
        return list(t.enums)
    return list(LEAD_STATUS_ORDER)


def build_lead_metadata_payload() -> dict[str, Any]:
    raw_values = lead_status_values_from_model()
    # Stable order: prefer LEAD_STATUS_ORDER, then any extra from DB
    ordered: list[str] = []
    for v in LEAD_STATUS_ORDER:
        if v in raw_values and v not in ordered:
            ordered.append(v)
    for v in raw_values:
        if v not in ordered:
            ordered.append(v)

    statuses = []
    for v in ordered:
        statuses.append(
            {
                "value": v,
                "label": LEAD_STATUS_LABELS.get(v, v.replace("_", " ").title()),
                "tone": LEAD_STATUS_TONES.get(v, "muted"),
            }
        )

    return {
        "statuses": statuses,
        "priorities": [dict(p) for p in PRIORITY_LEVELS],
    }
