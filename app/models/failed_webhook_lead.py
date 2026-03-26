"""Dead-letter storage for webhook payloads that could not become LeadCreate rows."""

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class FailedWebhookLead(MySQLBase):
    """Raw payload + error when ingestion fails (never silently drop data)."""

    __tablename__ = "failed_webhook_leads"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    source = Column(String(50), nullable=False, index=True)
    external_ref = Column(String(200), nullable=True, index=True)
    payload = Column(Text, nullable=False)
    error = Column(String(2000), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
