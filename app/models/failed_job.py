from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class FailedJob(MySQLBase):
    """Table to track background job failures for observability."""
    __tablename__ = "failed_jobs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    job_name = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    stack_trace = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
