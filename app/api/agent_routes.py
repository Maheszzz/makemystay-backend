"""API routes for Agent management."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.configs.db_config import get_mysql_db
from app.core import security
from app.repo import agent_repo
from app.schemas.agent_schema import AgentCreate, AgentResponse, AgentUpdate
from app.services.lead_service import update_lead_status

router = APIRouter(prefix="/agents", tags=["Agents"])


# ────────────────────────────────────────────────────────────────────
#  CRUD — Agents
# ────────────────────────────────────────────────────────────────────
@router.post("", response_model=AgentResponse, status_code=201)
def create_new_agent(
    agent_data: AgentCreate,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """Create a new agent (Admin only)."""
    try:
        return agent_repo.create_agent(db, agent_data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[AgentResponse])
def list_agents(
    active_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """List all agents (Admin only)."""
    return agent_repo.get_all_agents(
        db, skip=skip, limit=limit, active_only=active_only
    )


@router.get("/load")
def get_agent_workloads(
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """Return agent workloads summary (Admin only)."""
    agents = agent_repo.get_all_agents(db, active_only=True)
    return [
        {
            "agent_id": a.id,
            "name": a.name,
            "current_load": a.current_load,
            "max_capacity": a.max_capacity,
            "utilization": (
                round((a.current_load / a.max_capacity) * 100, 2)
                if a.max_capacity > 0
                else 0
            ),
        }
        for a in agents
    ]


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: int,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """Get agent details (Admin only)."""
    agent = agent_repo.get_agent_by_id(db, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent_details(
    agent_id: int,
    update_data: AgentUpdate,
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """Update agent details (Admin only)."""
    db_agent = agent_repo.get_agent_by_id(db, agent_id)
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent_repo.update_agent(db, db_agent, update_data)


# ────────────────────────────────────────────────────────────────────
#  Lead Status Update (with agent load management)
# ────────────────────────────────────────────────────────────────────
@router.patch("/leads/{lead_id}/status")
def update_lead_status_endpoint(
    lead_id: int,
    status: str = Query(..., description="New status: new, contacted, converted, lost"),
    db: Session = Depends(get_mysql_db),
    current_admin=Depends(security.admin_required),
):
    """
    Update a lead's status.

    When status becomes 'converted' or 'lost', the assigned agent's load
    is automatically decremented.
    """
    valid_statuses = {"new", "contacted", "converted", "lost"}
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(sorted(valid_statuses))}",
        )

    updated = update_lead_status(db, lead_id, status)
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {
        "status": "ok",
        "lead_id": updated.id,
        "new_status": updated.status,
        "assigned_to": updated.assigned_to,
    }
