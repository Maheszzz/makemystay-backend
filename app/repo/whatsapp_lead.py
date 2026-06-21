"""Repository layer for WhatsAppLead operations."""

from typing import List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.whatsapp_lead import WhatsAppLead


def create_whatsapp_lead(db: Session, lead_data: dict) -> WhatsAppLead:
    """Insert a new WhatsApp lead into the database."""
    try:
        db_lead = WhatsAppLead(**lead_data)
        db.add(db_lead)
        db.commit()
        db.refresh(db_lead)
        return db_lead
    except SQLAlchemyError:
        db.rollback()
        raise


def get_whatsapp_leads(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> List[WhatsAppLead]:
    """Retrieve WhatsApp leads with pagination."""
    return db.query(WhatsAppLead).order_by(WhatsAppLead.created_at.desc()).offset(skip).limit(limit).all()


def get_whatsapp_lead_by_id(db: Session, lead_id: int) -> Optional[WhatsAppLead]:
    """Retrieve a single WhatsApp lead by ID."""
    return db.query(WhatsAppLead).filter(WhatsAppLead.id == lead_id).first()
