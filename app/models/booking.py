from sqlalchemy import (
    DECIMAL,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.configs.db_config import MySQLBase


class Booking(MySQLBase):
    """
    A confirmed property reservation.

    A Booking is created when a customer initiates checkout and is linked to
    a Payment row via order_id.  The booking lifecycle:

      pending  → payment captured  → confirmed
               → payment failed    → cancelled
               → manual action     → completed / cancelled
    """

    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # --- Property & customer ---
    property_id = Column(
        Integer,
        ForeignKey("properties.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_name  = Column(String(100), nullable=True)
    customer_email = Column(String(150), nullable=True)
    customer_phone = Column(String(15),  nullable=True)

    # --- Booking details ---
    booking_type = Column(
        Enum("pg", "flat", "villa", "plot", "other", name="booking_type_enum"),
        default="pg",
        nullable=False,
    )
    move_in_date  = Column(DateTime, nullable=True)
    notes         = Column(Text, nullable=True)

    # --- Payment linkage ---
    # order_id links 1-to-1 with payments.order_id (the Razorpay order).
    order_id   = Column(String(100), unique=True, nullable=False, index=True)
    payment_id = Column(String(100), nullable=True, index=True)
    amount     = Column(DECIMAL(10, 2), nullable=True)
    currency   = Column(String(10), default="INR", nullable=False)

    # --- Status ---
    payment_status = Column(
        Enum("pending", "paid", "failed", "refunded", name="booking_payment_status_enum"),
        default="pending",
        nullable=False,
        index=True,
    )
    status = Column(
        Enum("pending", "confirmed", "completed", "cancelled", name="booking_status_enum"),
        default="pending",
        nullable=False,
        index=True,
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationship populated only when realty models are loaded in the same session.
    property = relationship("Property", lazy="select", foreign_keys=[property_id])
