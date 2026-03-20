from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class RetellCall(MySQLBase):
    """
    Normalized call logs for Retell AI outbound and inbound calls.
    Linked to a specific lead or completely freestanding (tests).
    """

    __tablename__ = "retell_calls"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    
    retell_call_id = Column(String(100), unique=True, index=True, nullable=True)
    to_phone = Column(String(50), nullable=False, index=True)
    from_number = Column(String(50), nullable=True)
    agent_id = Column(String(100), nullable=True)
    
    # queued, ringing, in_progress, completed, no_answer, failed
    status = Column(String(50), default="queued", index=True)
    
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    transcript = Column(Text, nullable=True)
    
    # Parsed Summaries
    summary_interested = Column(Boolean, nullable=True)
    summary_location = Column(String(200), nullable=True)
    summary_budget = Column(String(200), nullable=True)
    summary_move_in = Column(String(200), nullable=True)
    
    raw_webhook_payload = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    lead = relationship("Lead", back_populates="retell_calls")
