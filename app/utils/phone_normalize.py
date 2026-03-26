"""Normalize inbound webhook phone strings to Indian 10-digit mobile (LeadCreate pattern)."""

from typing import Optional


def normalize_to_indian_mobile_10(raw: str) -> Optional[str]:
    """
    Collapse to 10 digits starting 6–9 for ``LeadCreate.phone`` (``^[6-9]\\d{9}$``).

    Handles +91, spaces, and common portal formats. Returns None if not salvageable.
    """
    if not raw:
        return None
    s = raw.strip()
    if s.lower().startswith("whatsapp:"):
        s = s.replace("whatsapp:", "", 1).strip()
    digits = "".join(c for c in s if c.isdigit())
    if not digits:
        return None
    if len(digits) >= 12 and digits.startswith("91"):
        digits = digits[-10:]
    elif len(digits) > 10:
        digits = digits[-10:]
    if len(digits) != 10:
        return None
    if digits[0] not in "6789":
        return None
    return digits
