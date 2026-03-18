"""Service for lead status management and agent load balancing."""

from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.events.event_service import publish_event
from app.models.lead import Lead
from app.repo import agent_repo
from app.repo import lead as lead_repo

# Statuses that represent a "closed" lead (no longer active)
CLOSED_STATUSES = frozenset({"converted", "lost"})


def update_lead_status(db: Session, lead_id: int, status: str) -> Optional[Lead]:
    """
    Update lead status and handle agent load reduction when a lead is closed.

    When a lead moves to a "closed" state (converted / lost) and it was
    previously in an active state, the assigned agent's load is decremented
    to free up capacity for new leads.

    Args:
        db: Database session.
        lead_id: ID of the lead to update.
        status: New status value.

    Returns:
        Updated Lead object or None if lead not found.
    """
    db_lead = lead_repo.get_lead_by_id(db, lead_id)
    if not db_lead:
        return None

    old_status = db_lead.status
    db_lead.status = status

    # Handle load reduction when moving to a closed state
    if status in CLOSED_STATUSES and old_status not in CLOSED_STATUSES:
        if db_lead.assigned_to:
            agent_repo.update_agent_load(db, db_lead.assigned_to, -1)
            logger.info(
                f"Decremented load for Agent {db_lead.assigned_to} — "
                f"Lead {lead_id} closed ({status})"
            )
            publish_event(
                lead_id,
                "LEAD_CLOSED",
                f"Lead closed with status '{status}', agent load decremented",
            )

    db.commit()
    db.refresh(db_lead)

    publish_event(
        lead_id,
        "STATUS_UPDATED",
        f"Status changed: {old_status} → {status}",
    )
    return db_lead
