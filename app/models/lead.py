from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class Lead(MySQLBase):
    """Unified lead model — receives leads from all sources."""

    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=False, index=True)
    email = Column(String(200), nullable=True)
    source = Column(
        String(50), nullable=False, index=True
    )  # housing, 99acres, meta, website, etc.
    city = Column(String(100), nullable=True)
    location = Column(String(200), nullable=True)
    project_name = Column(String(300), nullable=True)
    property_type = Column(String(100), nullable=True)
    budget = Column(String(100), nullable=True)
    message = Column(Text, nullable=True)
    status = Column(
        Enum("new", "contacted", "qualified", "followup", "converted", "lost", name="lead_status_enum"),
        default="new",
        nullable=False,
        index=True,
    )
    crm_status = Column(
        String(20), default="pending", nullable=False, index=True
    )  # pending, queued, success, failed

    # Marketing Analytics
    campaign = Column(String(100), nullable=True)
    ad_id = Column(String(100), nullable=True)
    property_id = Column(String(100), nullable=True) # ID of specific property if lead is for one

    zoho_lead_id = Column(String(100), nullable=True)
    zoho_synced = Column(Boolean, default=False)
    is_ai_called = Column(Boolean, default=False)
    lead_date = Column(Integer, nullable=True, index=True)
    external_id = Column(String(100), nullable=True, index=True)
    raw_payload = Column(JSON, nullable=True)  # Store original payload for debugging
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Assignment
    assigned_to = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)
    priority = Column(Integer, default=1, index=True)

    # Relationships
    agent = relationship("Agent", back_populates="leads")
    retell_calls = relationship("RetellCall", back_populates="lead")

    __table_args__ = (
        UniqueConstraint(
            "phone", "lead_date", "external_id", name="uq_lead_phone_date_ext"
        ),
        UniqueConstraint("phone", "source", name="uq_lead_phone_source"),
        Index("ix_leads_status_created_at", "status", "created_at"),
    )
