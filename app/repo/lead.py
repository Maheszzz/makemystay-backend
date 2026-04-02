"""Repository layer for Lead operations."""

from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.models.agent import Agent


def create_lead(db: Session, lead_data: dict) -> Lead:
    """Insert a new lead into the database."""
    try:
        db_lead = Lead(**lead_data)
        db.add(db_lead)
        db.commit()
        db.refresh(db_lead)
        return db_lead
    except SQLAlchemyError:
        db.rollback()
        raise


def get_leads(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    source: Optional[str] = None,
    status: Optional[str] = None,
    assigned_to: Optional[int] = None,
) -> List[Lead]:
    """Retrieve leads with optional source/status filters and pagination."""
    query = db.query(Lead).order_by(Lead.created_at.desc())
    if source:
        query = query.filter(Lead.source == source)
    if status:
        query = query.filter(Lead.status == status)
    if assigned_to:
        query = query.filter(Lead.assigned_to == assigned_to)
    return query.offset(skip).limit(limit).all()


def get_lead_by_id(db: Session, lead_id: int) -> Optional[Lead]:
    """Retrieve a single lead by ID."""
    return db.query(Lead).filter(Lead.id == lead_id).first()


def get_lead_by_id_for_update(db: Session, lead_id: int) -> Optional[Lead]:
    """Retrieve a lead row with ``SELECT ... FOR UPDATE`` (serializes concurrent Zoho sync workers)."""
    return (
        db.query(Lead)
        .filter(Lead.id == lead_id)
        .with_for_update()
        .first()
    )


def get_lead_by_phone_source(db: Session, phone: str, source: str) -> Optional[Lead]:
    """Retrieve a single lead by phone + source."""
    return (
        db.query(Lead)
        .filter(Lead.phone == phone, Lead.source == source)
        .order_by(Lead.created_at.desc())
        .first()
    )


def update_lead(db: Session, db_lead: Lead, update_data: dict) -> Lead:
    """Update an existing lead."""
    try:
        for field, value in update_data.items():
            setattr(db_lead, field, value)
        db.commit()
        db.refresh(db_lead)
        return db_lead
    except SQLAlchemyError:
        db.rollback()
        raise
