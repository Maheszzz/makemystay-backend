"""
Zoho CRM Leads: Lead Status (parent) → Lead Substatus (child) mapping.

Single source of truth for admin UI and for resolving substatus → parent in code.
Align picklists in Zoho (Layout editor → field dependency) with these values.
"""

from __future__ import annotations

import re
from typing import Any

# (Parent Lead Status as in Zoho, tuple of Substatus values for that parent)
# Order matches the Zoho kanban / layout columns left-to-right where applicable.
ZOHO_LEAD_STATUS_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("None", ("None",)),
    (
        "New Lead / Prospect",
        (
            "Not_Reachable",
            "Not Connected",
            "Wrong Number",
            "WAP Sent",
            "WAP Not Delivered",
        ),
    ),
    ("Engaged", ("WAP Seen", "Hot Pipeline", "Existing customer")),
    ("Follow Up", ("Not Responding", "Call Back")),
    ("Visit Scheduled", ("Rescheduled SV", "Cancelled SV", "Visited")),
    (
        "Reserved",
        (
            "Checked-in",
            "Moved-in",
            "Checked out",
            "Cancelled Reservation",
            "Cancelled Checked-in",
            "Cancelled Moved-in",
        ),
    ),
    (
        "Dead",
        (
            "Property Mismatch",
            "Budget Mismatch",
            "Location Mismatch",
            "Service Issue",
            "Already Got Accomodation",
            "Not looking for Accomodation",
            "Short Term Stay",
            "Lost to Competitor",
            "Duplicate Lead",
        ),
    ),
    ("Video Visit", ("None",)),
    ("Ice Box", ("None",)),
)


def _norm_key(s: str) -> str:
    """Normalize for lookup: lowercase, collapse whitespace/underscores."""
    t = (s or "").strip().lower()
    t = re.sub(r"[\s_]+", "_", t)
    return t


def _build_substatus_to_parent() -> dict[str, str]:
    """First parent wins for duplicate substatus labels (e.g. ``None`` under multiple parents)."""
    out: dict[str, str] = {}
    for parent, subs in ZOHO_LEAD_STATUS_GROUPS:
        for sub in subs:
            key = _norm_key(sub)
            if key not in out:
                out[key] = parent
    return out


_SUBSTATUS_TO_PARENT = _build_substatus_to_parent()


def parent_for_zoho_substatus(substatus: str | None) -> str | None:
    """Return Zoho Lead Status (parent) for a given Lead Substatus, or None if unknown."""
    if substatus is None or not str(substatus).strip():
        return None
    return _SUBSTATUS_TO_PARENT.get(_norm_key(substatus))


def zoho_lead_status_from_pipeline_stage(lead_stage: str | None) -> str:
    """Map internal ``lead_stage`` (CRM pipeline) to Zoho ``Lead_Status`` parent picklist value."""
    s = (lead_stage or "new").strip().lower()
    return {
        "new": "New Lead / Prospect",
        "new lead / prospect": "New Lead / Prospect",
        "contacted": "Engaged",
        "interested": "Engaged",
        "visit_scheduled": "Visit Scheduled",
        "closed": "Reserved",
        "lost": "Dead",
    }.get(s, "New Lead / Prospect")


def default_zoho_substatus_for_parent(parent: str) -> str:
    """Default ``Lead_Substatus`` when DB ``sub_status`` is empty (must match Zoho picklist for that parent)."""
    p = (parent or "").strip()
    if p == "New Lead / Prospect":
        return "Not Connected"
    if p == "Engaged":
        return "WAP Seen"
    if p == "Follow Up":
        return "Call Back"
    if p == "Visit Scheduled":
        return "Visited"
    if p == "Reserved":
        return "Checked-in"
    if p == "Dead":
        return "Property Mismatch"
    if p == "None":
        return "None"
    if p == "Video Visit" or p == "Ice Box":
        return "None"
    return "Not Connected"


def build_zoho_lead_status_metadata() -> list[dict[str, Any]]:
    """Payload fragment for GET /admin/lead-metadata → ``zoho_lead_status``."""
    rows: list[dict[str, Any]] = []
    for parent, subs in ZOHO_LEAD_STATUS_GROUPS:
        children = [{"value": s, "label": s} for s in subs]
        rows.append({"parent": parent, "substatuses": children})
    return rows
