from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class LeadActivity(MySQLBase):
    """Unified activity timeline for a lead — tracks assignments, status changes, notes, calls."""

    __tablename__ = "lead_activities"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    type = Column(String(30), nullable=False, index=True)  # ASSIGNED, STATUS_CHANGED, NOTE, CALL, FOLLOWUP_SET, CREATED
    message = Column(Text, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    lead = relationship("Lead", back_populates="activities")
    user = relationship("User", foreign_keys=[created_by])
