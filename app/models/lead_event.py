from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class LeadEvent(MySQLBase):
    """Table to track all lifecycle events for a lead (Audit Log)."""
    __tablename__ = "lead_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)  # e.g., LEAD_CREATED, ASSIGNED, CRM_SYNC_SUCCESS
    message = Column(Text, nullable=True)
    payload = Column(Text, nullable=True) # Optional JSON string for extra data
    created_at = Column(DateTime(timezone=True), server_default=func.now())
