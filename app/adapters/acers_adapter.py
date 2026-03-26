"""Adapter: 99acres XML payload → internal LeadCreate schema.

Extracts and normalises fields from a 99acres ``<Qry>`` XML element
into the standard LeadCreate format used by the lead processing pipeline.
"""

import xml.etree.ElementTree as ET
from typing import Optional

from pydantic import ValidationError

from app.adapters.webhook_field_mapping import extract_phone_from_99acres_qry
from app.schemas.lead import LeadCreate
from app.utils.phone_normalize import normalize_to_indian_mobile_10


class AcersAdapter:
    """Maps a 99acres XML ``<Qry>`` element to a ``LeadCreate`` instance."""

    @staticmethod
    def qry_xml_string(qry: ET.Element) -> str:
        """Serialize one ``<Qry>`` block for dead-letter storage."""
        raw = ET.tostring(qry, encoding="unicode")
        return raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")

    @staticmethod
    def to_lead_create(qry: ET.Element) -> Optional[LeadCreate]:
        """Convert a single 99acres ``<Qry>`` XML element to a LeadCreate.

        Args:
            qry: An ``xml.etree.ElementTree.Element`` representing one
                 ``<Qry>`` block from the 99acres push webhook.

        Returns:
            A ``LeadCreate`` instance, or ``None`` if phone is missing or invalid.
        """

        def _text(tag: str) -> str:
            elem = qry.find(tag)
            return elem.text if elem is not None and elem.text else ""

        phone_raw = extract_phone_from_99acres_qry(qry)
        phone = normalize_to_indian_mobile_10(phone_raw) if phone_raw else None
        if not phone:
            return None

        # Build project name from available fields
        project_parts = []
        p_name = _text("ProjectName")
        p_code = _text("ProjectCode")
        p_generic = _text("Project")

        if p_name:
            project_parts.append(p_name)
        if p_code:
            project_parts.append(f"Code: {p_code}")
        if not p_name and p_generic:
            project_parts.append(p_generic)

        cmpct_val = _text("CmpctLabl")
        if cmpct_val:
            project_parts.append(f"[{cmpct_val}]")

        qry_id = _text("QryId")
        try:
            return LeadCreate(
                name=_text("Name") or "User",
                email=_text("Email") or None,
                phone=phone,
                message=_text("QryInfo") or _text("Message") or None,
                project_name=" | ".join(project_parts) if project_parts else None,
                external_id=qry_id or None,
            )
        except ValidationError:
            return None
