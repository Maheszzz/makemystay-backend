from sqlalchemy import Column, Integer, String, DateTime, Text, func
from app.configs.db_config import Base

class SyncJob(Base):
    """
    Persists Celery Background Task tracking into the internal DB for
    Admin UI observance, eliminating silent crashes from memory-bound queues.
    """
    __tablename__ = "sync_jobs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(255), unique=True, index=True, nullable=False)
    task_name = Column(String(255), nullable=False)
    status = Column(String(50), default="pending", index=True) # pending, running, success, failed
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
