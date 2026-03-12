"""SQLAlchemy model for tracking sync metadata (e.g., last fetch timestamp)."""

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class SyncMetadata(MySQLBase):
    """Tracks sync state for external integrations like Housing.com."""

    __tablename__ = "sync_metadata"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False, unique=True, index=True)
    last_lead_timestamp = Column(String(20), nullable=True)  # epoch string
    last_sync_at = Column(DateTime(timezone=True), server_default=func.now())
    leads_fetched = Column(Integer, default=0)
    leads_imported = Column(Integer, default=0)
    status = Column(String(20), default="active")  # active, error, stalled
    last_error = Column(String(500), nullable=True)
