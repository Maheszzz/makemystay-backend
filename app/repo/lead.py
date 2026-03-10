"""Repository layer for Lead operations."""

from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lead import Lead


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
) -> List[Lead]:
    """Retrieve leads with optional source/status filters and pagination."""
    query = db.query(Lead).order_by(Lead.created_at.desc())
    if source:
        query = query.filter(Lead.source == source)
    if status:
        query = query.filter(Lead.status == status)
    return query.offset(skip).limit(limit).all()


def get_lead_by_id(db: Session, lead_id: int) -> Optional[Lead]:
    """Retrieve a single lead by ID."""
    return db.query(Lead).filter(Lead.id == lead_id).first()


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
