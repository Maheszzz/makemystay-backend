from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text, func

from app.configs.db_config import MySQLBase


class PaymentWebhookEvent(MySQLBase):
    """Stores incoming Razorpay webhook callbacks for debugging and audits."""

    __tablename__ = "payment_webhook_events"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    provider = Column(String(50), nullable=False, default="razorpay")
    event = Column(String(120), nullable=True)
    status = Column(String(40), nullable=False)  # processed, ignored, rejected, error
    reason = Column(String(120), nullable=True)
    order_id = Column(String(100), nullable=True, index=True)
    payment_id = Column(String(100), nullable=True, index=True)
    signature_valid = Column(Boolean, nullable=False, default=False)
    signature_header = Column(String(255), nullable=True)
    payload = Column(JSON, nullable=True)
    raw_body = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
