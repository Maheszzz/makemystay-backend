"""Adapter: Housing.com raw payload → internal LeadCreate schema.

Extracts and normalises fields from the Housing.com Pahal API response
into the standard LeadCreate format used by the lead processing pipeline.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.schemas.lead import LeadCreate


class HousingAdapter:
    """Maps a raw Housing.com lead dict to a ``LeadCreate`` instance."""

    @staticmethod
    def to_lead_create(raw: Dict[str, Any]) -> Optional[LeadCreate]:
        """Convert a Housing.com API lead to the internal schema.

        Args:
            raw: Single lead dict as returned by the Pahal API.

        Returns:
            A ``LeadCreate`` instance, or ``None`` if phone is missing/invalid.
        """
        phone = raw.get("lead_phone", "")
        if not phone or len(phone) < 10:
            return None

        # Build a contextual message from extra fields
        parts: List[str] = []
        if raw.get("service_type"):
            parts.append(f"Service: {raw['service_type']}")
        if raw.get("category_type"):
            parts.append(f"Category: {raw['category_type']}")
        if raw.get("apartment_names"):
            parts.append(f"Config: {raw['apartment_names']}")
        if raw.get("pg_name"):
            parts.append(f"PG: {raw['pg_name']}")
        if raw.get("locality_name"):
            parts.append(f"Locality: {raw['locality_name']}")
        if raw.get("city_name"):
            parts.append(f"City: {raw['city_name']}")

        project_id = raw.get("project_id") or raw.get("flat_id")
        if project_id:
            parts.append(f"Project/Flat ID: {project_id}")

        # Budget range
        min_price = raw.get("min_price")
        max_price = raw.get("max_price")
        if min_price and max_price:
            parts.append(f"Budget: ₹{min_price} - ₹{max_price}")
        elif min_price:
            parts.append(f"Budget: ₹{min_price}+")

        # Property field (e.g. ["Apartment"])
        prop_field = raw.get("property_field")
        if prop_field and isinstance(prop_field, list):
            parts.append(f"Type: {', '.join(prop_field)}")

        lead_date = raw.get("lead_date")
        if lead_date:
            try:
                dt = datetime.fromtimestamp(int(lead_date))
                parts.append(f"Lead Date: {dt.strftime('%Y-%m-%d %H:%M')}")
            except (ValueError, TypeError, OSError):
                parts.append(f"Lead Date: {lead_date}")

        # Location: prefer locality_name, fall back to city_name
        location = raw.get("locality_name") or raw.get("city_name")

        # Property type: combine service_type + apartment_names
        property_type = raw.get("service_type", "")
        if raw.get("apartment_names"):
            property_type = f"{raw['apartment_names']} ({property_type})"

        # Budget string
        budget: Optional[str] = None
        if min_price and max_price:
            budget = f"₹{min_price} - ₹{max_price}"
        elif min_price:
            budget = f"₹{min_price}+"

        return LeadCreate(
            name=raw.get("lead_name"),
            phone=phone,
            email=raw.get("lead_email"),
            project_name=raw.get("project_name"),
            location=location,
            property_type=property_type,
            budget=budget,
            message=" | ".join(parts) if parts else None,
            lead_date=lead_date,
            external_id=str(raw.get("flat_id")) if raw.get("flat_id") else None,
        )
