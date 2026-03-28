import json
from typing import Any

from app.core.config import settings
from app.core.zoho_lead_status_mapping import (
    default_zoho_substatus_for_parent,
    zoho_lead_status_from_pipeline_stage,
)

# Lead Status / Substatus picklist dependency: see ``app.core.zoho_lead_status_mapping``.

# ------------------------------------------------------------------ #
#  Human-friendly source names for Zoho CRM Lead_Source
# ------------------------------------------------------------------ #
SOURCE_DISPLAY_NAMES = {
    "housing": "Housing.com",
    "99acres": "99acres",
    "magicbricks": "MagicBricks",
    "meta": "Meta Ads",
    "website": "Website",
    "broker": "Broker Referral",
}


def _get_display_source(source: str) -> str:
    """Return a display-friendly source name for CRM."""
    return SOURCE_DISPLAY_NAMES.get(source.lower(), source.title())


def _infer_lead_type(property_type: str) -> str:
    """Default Zoho Lead_Type when no explicit value (common values: Rental, Sale)."""
    pt = (property_type or "").lower()
    if any(x in pt for x in ("sale", "buy", "purchase", "resale")):
        return "Sale"
    return "Rental"


def _coerce_zoho_picklist_and_numeric(
    payload: dict[str, Any],
    *,
    preferred_field: str,
    lead_type_field: str,
    inquiry_field: str,
) -> None:
    """Zoho expects strict types — strings for picklists, int for Inquiry_Count."""
    payload["Lead_Status"] = str(payload["Lead_Status"])
    payload["Lead_Substatus"] = str(payload["Lead_Substatus"])
    if preferred_field in payload:
        payload[preferred_field] = str(payload[preferred_field])[:500]
    payload[lead_type_field] = str(payload[lead_type_field])[:120]
    raw_inq = payload.get(inquiry_field, 1)
    try:
        payload[inquiry_field] = int(max(1, int(raw_inq or 1)))
    except (TypeError, ValueError):
        payload[inquiry_field] = 1


def _omit_none(d: dict[str, Any]) -> dict[str, Any]:
    """Zoho ignores or errors on nulls — drop keys whose value is None."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, dict):
            nested = _omit_none(v)
            if nested:
                out[k] = nested
        else:
            out[k] = v
    return out


class CRMLeadAdapter:
    """Maps a Lead (or payload) to Zoho CRM Leads module field API names."""

    def __init__(self, payload: Any, source: str):
        self.name_ = getattr(payload, "name_", getattr(payload, "name", "Lead"))
        self.name = self.name_
        self.phone = getattr(payload, "phone", "") or ""
        self.email = getattr(payload, "email", "") or ""
        self.company = "Individual"

        self.city = (getattr(payload, "city", None) or "") or ""
        self.location = (getattr(payload, "location", None) or "") or ""
        self.project_name = (getattr(payload, "project_name", None) or "") or ""
        self.property_type = getattr(payload, "property_type", "") or ""
        self.units = getattr(payload, "units", "") or ""

        parts = []
        msg = getattr(payload, "message", "")
        if msg:
            parts.append(str(msg).strip())
        req = getattr(payload, "requirement", "")
        if req:
            parts.append(f"Requirement: {req}")
        if self.project_name:
            parts.append(f"Project: {self.project_name}")
        budg = getattr(payload, "budget", "")
        if budg:
            parts.append(f"Budget: {budg}")
        self.message = " | ".join(parts) if parts else ""

        self.lead_source = _get_display_source(source)

        self.interested = getattr(payload, "interested", getattr(payload, "summary_interested", None))
        self.call_status = getattr(payload, "call_status", "")
        self.summary_budget = getattr(payload, "summary_budget", "")
        self.owner_zoho_id = getattr(payload, "owner_zoho_id", None)

        # Internal CRM pipeline (new, contacted, …) — not Zoho UI labels
        self.lead_stage = getattr(payload, "lead_stage", None) or "new"
        self.sub_status = getattr(payload, "sub_status", None)
        self.inquiry_count = int(getattr(payload, "inquiry_count", 1) or 1)
        self.lead_type = getattr(payload, "lead_type", None)
        self.preferred_location = getattr(payload, "preferred_location", None)
        # Existing Zoho record id — used first for PUT so all fields refresh (not only phone/email match).
        self.zoho_lead_id = getattr(payload, "zoho_lead_id", None)

        self.raw_data = payload

    def _preferred_location_line(self) -> str:
        pl = self.preferred_location
        if pl is not None and str(pl).strip():
            return str(pl).strip()[:500]
        city = self.city.strip()
        loc = self.location.strip()
        if city and loc and city.upper() != loc.upper():
            return f"{city}, {loc}"[:500]
        if loc:
            return loc[:500]
        if city:
            return city[:500]
        return ""

    def to_zoho_payload(self) -> dict[str, Any]:
        """Map internal fields to Zoho CRM Lead field API names (must match Setup → Leads → Fields)."""
        first_name = ""
        last_name = "User"

        if self.name_:
            names = str(self.name_).strip().split(" ", 1)
            if len(names) > 1:
                first_name, last_name = names[0], names[1]
            elif names[0]:
                last_name = names[0]

        if not last_name or not str(last_name).strip():
            last_name = "Unknown"

        city_val = (self.city or self.location or "").strip()
        proj = self.project_name.strip()

        lead_source_line = self.lead_source
        if proj:
            lead_source_line = f"{self.lead_source} — {proj}"[:255]

        description_parts = []
        if self.message:
            description_parts.append(f"Query: {self.message}")
        if proj:
            description_parts.append(f"Project: {proj}")
        loc = self.location.strip()
        if loc and city_val and loc.upper() != city_val.upper():
            description_parts.append(f"Area / Locality: {loc}")
        if self.property_type:
            description_parts.append(f"Property Type: {self.property_type}")
        if self.units:
            description_parts.append(f"Units: {self.units}")

        description = " | ".join(description_parts) if description_parts else ""

        lead_status = zoho_lead_status_from_pipeline_stage(self.lead_stage)
        sub_raw = (self.sub_status or "").strip()
        lead_substatus = sub_raw if sub_raw else default_zoho_substatus_for_parent(lead_status)

        preferred_field = (getattr(settings, "ZOHO_CRM_PREFERRED_LOCATION_FIELD", None) or "Preferred_Location").strip()
        lead_type_field = (getattr(settings, "ZOHO_CRM_LEAD_TYPE_FIELD", None) or "Lead_Type").strip()
        inquiry_field = (getattr(settings, "ZOHO_CRM_INQUIRY_COUNT_FIELD", None) or "Inquiry_Count").strip()

        lead_type_val = (self.lead_type or "").strip() or _infer_lead_type(self.property_type)

        payload: dict[str, Any] = {
            "First_Name": first_name[:40],
            "Last_Name": last_name[:80],
            "Email": (self.email or "")[:100],
            "Phone": self.phone[:30],
            "Company": self.company,
            "Description": description[:32000],
            "Lead_Source": lead_source_line,
            "City": city_val[:255],
            # Exact API names (Zoho Leads module)
            "Lead_Status": lead_status,
            "Lead_Substatus": lead_substatus,
        }

        pref = self._preferred_location_line()
        if pref:
            payload[preferred_field] = pref

        payload[lead_type_field] = lead_type_val[:120]
        payload[inquiry_field] = max(1, self.inquiry_count)

        budget_field = (getattr(settings, "ZOHO_CRM_BUDGET_FIELD", None) or "Budget").strip()
        effective_budget = (self.summary_budget or getattr(self.raw_data, "budget", None) or "") or ""
        if effective_budget and budget_field:
            payload[budget_field] = str(effective_budget)[:200]

        if self.interested is not None:
            payload["AI_Interested"] = self.interested

        if self.call_status:
            payload["AI_Call_Status"] = self.call_status

        if self.summary_budget and "AI_Budget" not in payload:
            payload["AI_Budget"] = self.summary_budget

        if self.owner_zoho_id:
            payload["Owner"] = {"id": str(self.owner_zoho_id)}

        if not payload.get("Lead_Status"):
            raise ValueError("Zoho sync: missing Lead_Status after mapping (check lead_stage / Zoho mapping).")

        _coerce_zoho_picklist_and_numeric(
            payload,
            preferred_field=preferred_field,
            lead_type_field=lead_type_field,
            inquiry_field=inquiry_field,
        )

        # Final cleanup and logging
        for k in ["Lead_Status", "Lead_Substatus"]:
            if k in payload and isinstance(payload[k], str):
                payload[k] = payload[k].strip()

        return _omit_none(payload)

    def to_zoho_payload_json_for_debug(self) -> str:
        """Pretty JSON for logs (safe for Celery / support)."""
        try:
            return json.dumps(self.to_zoho_payload(), default=str, indent=2)
        except Exception as e:
            return json.dumps({"error": str(e)})

