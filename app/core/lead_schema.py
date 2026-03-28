"""
Single source of truth for lead statuses, priorities, and labels.
Keep in sync with app.models.lead.Lead status Enum column.
"""

from __future__ import annotations

from typing import Any

from app.core.lead_pipeline import VALID_LEAD_STAGES
from app.core.zoho_lead_status_mapping import build_zoho_lead_status_metadata

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

# CRM pipeline (PUT /leads/{id}/stage) — must match app.core.lead_pipeline.VALID_LEAD_STAGES
LEAD_STAGE_ORDER: tuple[str, ...] = (
    "New Lead / Prospect",
    "Engaged",
    "Follow Up",
    "Visit Scheduled",
    "Reserved",
    "Dead",
)

LEAD_STAGE_LABELS: dict[str, str] = {
    "New Lead / Prospect": "New Lead / Prospect",
    "Engaged": "Engaged",
    "Follow Up": "Follow Up",
    "Visit Scheduled": "Visit Scheduled",
    "Reserved": "Reserved",
    "Dead": "Dead",
    "new": "New",
    "contacted": "Contacted",
}

LEAD_STAGE_TONES: dict[str, str] = {
    "new": "warning",
    "contacted": "info",
    "interested": "success",
    "visit_scheduled": "cyan",
    "closed": "positive",
    "lost": "muted",
}

# Website contact form (contacts.status enum) — admin UI only
CONTACT_STATUS_ORDER: tuple[str, ...] = ("new", "contacted", "closed")
CONTACT_STATUS_LABELS: dict[str, str] = {
    "new": "New",
    "contacted": "Contacted",
    "closed": "Closed",
}
CONTACT_STATUS_TONES: dict[str, str] = {
    "new": "warning",
    "contacted": "info",
    "closed": "muted",
}


def lead_status_values_from_model() -> list[str]:
    """Read enum members from the Lead ORM column (matches MySQL enum)."""
    from app.models.lead import Lead

    col = Lead.__table__.c.status
    t = col.type
    if hasattr(t, "enums") and t.enums:
        return list(t.enums)
    return list(LEAD_STATUS_ORDER)


def contact_status_values_from_model() -> list[str]:
    """Read enum members from Contact.status (matches MySQL contact_status enum)."""
    from app.models.realty import Contact

    col = Contact.__table__.c.status
    t = col.type
    if hasattr(t, "enums") and t.enums:
        return list(t.enums)
    return list(CONTACT_STATUS_ORDER)


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

    # Pipeline stages (CRM) — order from LEAD_STAGE_ORDER, values must exist in VALID_LEAD_STAGES
    stage_ordered: list[str] = []
    for v in LEAD_STAGE_ORDER:
        if v in VALID_LEAD_STAGES and v not in stage_ordered:
            stage_ordered.append(v)
    for v in sorted(VALID_LEAD_STAGES):
        if v not in stage_ordered:
            stage_ordered.append(v)

    stages: list[dict[str, Any]] = []
    for v in stage_ordered:
        stages.append(
            {
                "value": v,
                "label": LEAD_STAGE_LABELS.get(v, v.replace("_", " ").title()),
                "tone": LEAD_STAGE_TONES.get(v, "muted"),
            }
        )

    raw_contact = contact_status_values_from_model()
    contact_ordered: list[str] = []
    for v in CONTACT_STATUS_ORDER:
        if v in raw_contact and v not in contact_ordered:
            contact_ordered.append(v)
    for v in raw_contact:
        if v not in contact_ordered:
            contact_ordered.append(v)

    contact_statuses: list[dict[str, Any]] = []
    for v in contact_ordered:
        contact_statuses.append(
            {
                "value": v,
                "label": CONTACT_STATUS_LABELS.get(v, v.replace("_", " ").title()),
                "tone": CONTACT_STATUS_TONES.get(v, "muted"),
            }
        )

    return {
        "statuses": statuses,
        "priorities": [dict(p) for p in PRIORITY_LEVELS],
        "stages": stages,
        "contact_statuses": contact_statuses,
        "zoho_lead_status": build_zoho_lead_status_metadata(),
    }
