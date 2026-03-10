from sqlalchemy import DECIMAL, Column, DateTime, Enum, Integer, String, func

from app.configs.db_config import MySQLBase


class Payment(MySQLBase):
    """Model for payments table"""

    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(10), default="INR", nullable=False)
    payment_type = Column(String(50), default="booking", nullable=False)
    status = Column(
        Enum("pending", "success", "failed", "expired", name="payment_status_enum"),
        default="pending",
        nullable=False,
    )
    order_id = Column(String(100), unique=True, nullable=False, index=True)
    payment_id = Column(String(100), nullable=True)
    signature = Column(String(255), nullable=True)

    # Payer details
    payer_name = Column(
        String(100), nullable=True
    )  # Optional as we might not have it initially
    payer_email = Column(String(150), nullable=True)
    payer_phone = Column(String(15), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
