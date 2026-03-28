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
        Enum(
            "new", "contacted", "qualified", "followup", "converted", "lost",
            "interested", "not_interested",
            name="lead_status_enum",
        ),
        default="new",
        nullable=False,
        index=True,
    )
    crm_status = Column(
        String(20), default="pending", nullable=False, index=True
    )  # pending, queued, success, failed, retrying, permanently_failed (Zoho sync lifecycle)

    # Pipeline stages (CRM): new → contacted → interested → visit_scheduled → closed
    lead_stage = Column(String(50), default="new", nullable=False, index=True)
    sub_status = Column(String(100), nullable=True, index=True)
    last_contacted_at = Column(DateTime(timezone=True), nullable=True)
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)
    
    inquiry_count = Column(Integer, default=1, nullable=False)
    reentry_count = Column(Integer, default=0, nullable=False)

    # Marketing Analytics
    campaign = Column(String(100), nullable=True)
    ad_id = Column(String(100), nullable=True)
    property_id = Column(String(100), nullable=True) # ID of specific property if lead is for one

    zoho_lead_id = Column(String(100), nullable=True)
    zoho_synced = Column(Boolean, default=False)
    is_ai_called = Column(Boolean, default=False)
    whatsapp_sent = Column(Boolean, default=False)
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
    
    # Ownership (Admin -> RM)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    assigned_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)

    # Follow-up scheduling
    follow_up_at = Column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    agent = relationship("Agent", back_populates="leads")
    owner = relationship("User", back_populates="leads")
    assigned_employee = relationship("Employee", back_populates="leads")
    retell_calls = relationship("RetellCall", back_populates="lead")
    assignments = relationship("LeadAssignment", back_populates="lead", order_by="LeadAssignment.assigned_at.desc()")
    activities = relationship("LeadActivity", back_populates="lead", order_by="LeadActivity.created_at.desc()")
    # Elite Improvements (FINAL 1%)
    normalized_phone = Column(String(20), unique=True, index=True)
    last_reentry_at = Column(DateTime, nullable=True)
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("unique_normalized_phone", "normalized_phone", unique=True),
        Index("idx_phone_stage", "normalized_phone", "lead_stage"),
        # Dedup: same inquiry = same phone + same lead timestamp + same external reference.
        UniqueConstraint(
            "phone", "lead_date", "external_id", name="uq_lead_phone_date_ext"
        ),
        # Strict protection against duplicate floods for the same property on the same day
        UniqueConstraint(
            "phone", "property_id", "lead_date", name="uq_lead_phone_property_date"
        ),
        Index("ix_leads_status_created_at", "status", "created_at"),
    )
