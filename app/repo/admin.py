"""Repository layer for Administrative dashboard operations."""

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.realty import Contact, Property


def get_dashboard_stats(db: Session):
    """Calculate aggregate metrics for the admin dashboard."""
    total_leads = 0
    total_properties = db.query(func.count(Property.id)).filter(Property.is_deleted.is_(False)).scalar() or 0
    total_contacts = db.query(func.count(Contact.id)).scalar() or 0
    total_ai_calls = 0
    active_listings = db.query(func.count(Property.id)).filter(
        Property.is_available.is_(True),
        Property.is_deleted.is_(False)
    ).scalar() or 0

    return {
        "total_leads": total_leads,
        "total_properties": total_properties,
        "total_contacts": total_contacts,
        "total_ai_calls": total_ai_calls,
        "active_listings": active_listings
    }

def get_live_leads(db: Session, limit: int = 10):
    return []

def global_search(db: Session, query: str):
    """Search for properties and leads matching the query."""
    search_term = f"%{query}%"

    properties = db.query(Property).filter(
        Property.is_deleted.is_(False),
        or_(
            Property.property_name.ilike(search_term),
            Property.location.ilike(search_term)
        )
    ).limit(10).all()

    leads = []

    return {
        "properties": properties,
        "leads": leads
    }
