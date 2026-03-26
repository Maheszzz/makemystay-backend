"""Configurable field names for webhook adapters (sources change tags without notice)."""

import xml.etree.ElementTree as ET
from typing import List

# Ordered: first match wins (99acres XML tag names are inconsistent across campaigns).
PHONE_FIELDS_99ACRES: List[str] = [
    "Mobile",
    "Phone",
    "Phone1",
    "Tel",
    "ContactNumber",
    "PhoneNumber",
    "MobileNumber",
]

# Future: housing JSON keys, etc.
PHONE_FIELDS_BY_SOURCE = {
    "99acres": PHONE_FIELDS_99ACRES,
}


def _qry_text(qry: ET.Element, tag: str) -> str:
    elem = qry.find(tag)
    return elem.text.strip() if elem is not None and elem.text else ""


def extract_phone_from_99acres_qry(qry: ET.Element) -> str:
    """Return first non-empty phone string from a ``<Qry>`` element (not yet normalized)."""
    for field in PHONE_FIELDS_99ACRES:
        val = _qry_text(qry, field)
        if val:
            return val
    return ""
