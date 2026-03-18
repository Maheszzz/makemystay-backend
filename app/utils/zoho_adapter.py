from typing import Any

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
    """Maps a Lead payload to the attribute interface expected by ZohoCRMService."""
    def __init__(self, payload: Any, source: str):
        # Handle both Pydantic models (with name_) and regular dicts/objects
        self.name_ = getattr(payload, "name_", getattr(payload, "name", "Lead"))
        self.name = self.name_
        self.phone = getattr(payload, "phone", "")
        self.email = getattr(payload, "email", "")
        self.company = "Individual"

        parts = []
        msg = getattr(payload, "message", "")
        if msg: parts.append(msg)
        req = getattr(payload, "requirement", "")
        if req: parts.append(f"Requirement: {req}")
        proj = getattr(payload, "project_name", "")
        if proj: parts.append(f"Project: {proj}")
        budg = getattr(payload, "budget", "")
        if budg: parts.append(f"Budget: {budg}")
        self.message = " | ".join(parts) if parts else ""

        self.location = getattr(payload, "location", getattr(payload, "city", ""))
        self.property_type = getattr(payload, "property_type", "")
        self.units = getattr(payload, "units", "")
        self.lead_source = _get_display_source(source)

        # Store raw payload for fallback
        self.raw_data = payload

    def to_zoho_payload(self) -> dict:
        """Map internal fields to Zoho CRM field names."""
        # Parse name
        first_name = ""
        last_name = "User"  # Zoho requires Last Name

        if self.name_:
            names = self.name_.split(" ", 1)
            if len(names) > 1:
                first_name, last_name = names[0], names[1]
            else:
                last_name = names[0]

        description_parts = []
        if self.message:
            description_parts.append(f"Message: {self.message}")
        if self.location:
            description_parts.append(f"Location: {self.location}")
        if self.property_type:
            description_parts.append(f"Property Type: {self.property_type}")
        if self.units:
            description_parts.append(f"Units: {self.units}")

        description = " | ".join(description_parts) if description_parts else ""

        return {
            "First_Name": first_name,
            "Last_Name": last_name,
            "Email": self.email,
            "Phone": self.phone,
            "Company": self.company,
            "Description": description,
            "Lead_Source": self.lead_source,
            "City": self.location,
        }
