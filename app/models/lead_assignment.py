from sqlalchemy import Column, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class LeadAssignment(MySQLBase):
    """Audit log for lead assignments — tracks who assigned which lead to which RM."""

    __tablename__ = "lead_assignments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    assigned_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    lead = relationship("Lead", back_populates="assignments")
    assigner = relationship("User", foreign_keys=[assigned_by])
    assignee = relationship("User", foreign_keys=[assigned_to])
