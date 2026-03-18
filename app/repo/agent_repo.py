"""Repository layer for Agent operations."""

from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.agent import Agent
from app.schemas.agent_schema import AgentCreate, AgentUpdate


def create_agent(db: Session, agent_data: AgentCreate) -> Agent:
    """Create a new agent."""
    db_agent = Agent(**agent_data.model_dump())
    db.add(db_agent)
    try:
        db.commit()
        db.refresh(db_agent)
        return db_agent
    except SQLAlchemyError:
        db.rollback()
        raise


def get_agent_by_id(db: Session, agent_id: int) -> Optional[Agent]:
    """Get an agent by ID."""
    return db.query(Agent).filter(Agent.id == agent_id).first()


def get_all_agents(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = False,
) -> List[Agent]:
    """List all agents."""
    query = db.query(Agent)
    if active_only:
        query = query.filter(Agent.is_active == True)  # noqa: E712
    return query.offset(skip).limit(limit).all()


def get_available_agents_for_update(
    db: Session,
    location: Optional[str] = None,
) -> List[Agent]:
    """
    Fetch active agents under capacity with SELECT FOR UPDATE row-level lock.

    This MUST be called inside an active transaction so the lock is held
    until commit/rollback. The lock prevents two concurrent workers from
    reading the same agent load and double-assigning.

    Args:
        db: Active SQLAlchemy session (inside a transaction).
        location: Optional location filter for the lead.

    Returns:
        List of Agent rows that are active and under max_capacity.
    """
    query = (
        db.query(Agent)
        .filter(
            Agent.is_active == True,  # noqa: E712
            Agent.current_load < Agent.max_capacity,
        )
        .with_for_update()  # SELECT ... FOR UPDATE
    )

    if location:
        query = query.filter(Agent.location.ilike(f"%{location}%"))

    return query.all()


def update_agent(db: Session, db_agent: Agent, update_data: AgentUpdate) -> Agent:
    """Update agent details."""
    data = update_data.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(db_agent, field, value)
    try:
        db.commit()
        db.refresh(db_agent)
        return db_agent
    except SQLAlchemyError:
        db.rollback()
        raise


def update_agent_load(db: Session, agent_id: int, delta: int) -> Optional[Agent]:
    """Safely update agent's current load.

    Can be used standalone (will commit) or inside an existing transaction
    (caller is responsible for committing).
    """
    db_agent = get_agent_by_id(db, agent_id)
    if db_agent:
        db_agent.current_load = max(0, db_agent.current_load + delta)
        try:
            db.commit()
            db.refresh(db_agent)
            return db_agent
        except SQLAlchemyError:
            db.rollback()
            raise
    return None
