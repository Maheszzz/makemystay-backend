"""Rule-based CRM employee (RM) assignment from city / locality (JSON config)."""

from __future__ import annotations

import json
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.employee import Employee
from app.models.lead import Lead


def try_assign_employee_by_city_rules(db: Session, lead: Lead) -> None:
    """
    If ``CRM_CITY_EMPLOYEE_JSON`` maps a city name to ``employees.id``, assign that RM.

    Example env (single line JSON):
    ``{"BTM": 1, "HSR": 2, "BANGALORE": 3}``
    Keys are matched case-insensitively; substring match if the key appears in city/location.
    Skips when a CRM employee is already assigned (preserve manual assignment).
    """
    if getattr(lead, "assigned_employee_id", None):
        return

    raw = (getattr(settings, "CRM_CITY_EMPLOYEE_JSON", None) or "").strip()
    if not raw or raw == "{}":
        return
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("CRM_CITY_EMPLOYEE_JSON is not valid JSON: {}", e)
        return
    if not isinstance(mapping, dict):
        return

    haystack = f"{lead.city or ''} {lead.location or ''}".strip().upper()
    if not haystack:
        return

    chosen_id: Optional[int] = None
    for k, v in mapping.items():
        key = str(k).strip().upper()
        if not key:
            continue
        if key in haystack:
            try:
                chosen_id = int(v)
            except (TypeError, ValueError):
                continue
            break

    if not chosen_id:
        return

    emp = (
        db.query(Employee)
        .filter(Employee.id == chosen_id, Employee.status == "active")
        .first()
    )
    if not emp:
        logger.warning("CRM city rule points to missing/inactive employee id={}", chosen_id)
        return

    lead.assigned_employee_id = emp.id
    if emp.user_id is not None:
        lead.owner_id = emp.user_id
