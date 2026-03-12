from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
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
        Enum("new", "contacted", "converted", "lost", name="lead_status_enum"),
        default="new",
        nullable=False,
        index=True,
    )
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

    __table_args__ = (
        UniqueConstraint(
            "phone", "lead_date", "external_id", name="uq_lead_phone_date_ext"
        ),
    )
