from typing import Any

from app.core.config import settings

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

        self.raw_data = payload

    def to_zoho_payload(self) -> dict:
        """Map internal fields to Zoho CRM Lead field names (Last Name, Phone, Email, City, etc.)."""
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

        payload = {
            "First_Name": first_name[:40],
            "Last_Name": last_name[:80],
            "Email": (self.email or "")[:100],
            "Phone": self.phone[:30],
            "Company": self.company,
            "Description": description[:32000],
            "Lead_Source": lead_source_line,
            "City": city_val[:255],
        }

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

        return payload
