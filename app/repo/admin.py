"""Repository layer for Administrative dashboard operations."""

from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.lead import Lead
from app.models.realty import Property, Contact

def get_dashboard_stats(db: Session):
    """Calculate aggregate metrics for the admin dashboard."""
    total_leads = db.query(func.count(Lead.id)).scalar() or 0
    total_properties = db.query(func.count(Property.id)).filter(Property.is_deleted == False).scalar() or 0
    total_contacts = db.query(func.count(Contact.id)).scalar() or 0
    total_ai_calls = db.query(func.count(Lead.id)).filter(Lead.is_ai_called == True).scalar() or 0
    active_listings = db.query(func.count(Property.id)).filter(
        Property.is_available == True, 
        Property.is_deleted == False
    ).scalar() or 0

    return {
        "total_leads": total_leads,
        "total_properties": total_properties,
        "total_contacts": total_contacts,
        "total_ai_calls": total_ai_calls,
        "active_listings": active_listings
    }

def get_live_leads(db: Session, limit: int = 10):
    """Fetch the most recent leads for the live feed."""
    return db.query(Lead).order_by(Lead.created_at.desc()).limit(limit).all()
