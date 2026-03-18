"""Adapter: 99acres XML payload → internal LeadCreate schema.

Extracts and normalises fields from a 99acres ``<Qry>`` XML element
into the standard LeadCreate format used by the lead processing pipeline.
"""

import xml.etree.ElementTree as ET
from typing import Optional

from app.schemas.lead import LeadCreate


class AcersAdapter:
    """Maps a 99acres XML ``<Qry>`` element to a ``LeadCreate`` instance."""

    @staticmethod
    def to_lead_create(qry: ET.Element) -> Optional[LeadCreate]:
        """Convert a single 99acres ``<Qry>`` XML element to a LeadCreate.

        Args:
            qry: An ``xml.etree.ElementTree.Element`` representing one
                 ``<Qry>`` block from the 99acres push webhook.

        Returns:
            A ``LeadCreate`` instance, or ``None`` if phone is missing.
        """

        def _text(tag: str) -> str:
            elem = qry.find(tag)
            return elem.text if elem is not None and elem.text else ""

        phone = _text("Phone")
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

        return LeadCreate(
            name=_text("Name") or "User",
            email=_text("Email") or None,
            phone=phone,
            message=_text("QryInfo") or None,
            project_name=" | ".join(project_parts) if project_parts else None,
        )
