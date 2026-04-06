from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Index
from app.configs.db_config import Base

class ZohoWebhookEvent(Base):
    """Stores incoming Zoho CRM webhook events for idempotency and audit trails.
    
    This ensures that each unique Zoho event is processed exactly once, protecting 
    against accidental duplicate syncs and providing a clear log of inbound changes.
    """
    __tablename__ = "zoho_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    
    # event_id is typically the Zoho Record ID or a specific event UUID
    event_id = Column(String(100), unique=True, index=True, nullable=False)
    
    # event_type can be: lead_create, lead_update, lead_delete (Elite observability)
    event_type = Column(String(50), nullable=True, index=True)
    
    source = Column(String(50), default="zoho", index=True)
    payload = Column(JSON, nullable=False)
    
    # status can be: pending, processing, processed, failed
    status = Column(String(20), default="pending", index=True)
    
    # Tracking for DLQ and Performance (Elite hardening)
    retry_count = Column(Integer, default=0)
    processing_time_ms = Column(Integer, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_zoho_webhook_events_status_created", "status", "created_at"),
    )

    def __repr__(self):
        return f"<ZohoWebhookEvent(id={self.id}, event_id={self.event_id}, status={self.status})>"
