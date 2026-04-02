"""DLQ rows for Zoho lead sync — permanent failures for manual replay."""

from sqlalchemy import Column, DateTime, Integer, JSON, Text
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class FailedZohoTask(MySQLBase):
    __tablename__ = "failed_zoho_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    lead_id = Column(Integer, nullable=False, index=True)
    error = Column(Text, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
