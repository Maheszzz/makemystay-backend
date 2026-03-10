from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.configs.db_config import MySQLBase

class DemoBooking(MySQLBase):
    __tablename__ = "demo_bookings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    company = Column(String(255), nullable=True)
    units = Column(String(50), nullable=True)
    selected_slot = Column(DateTime, nullable=False)
    status = Column(String(50), default="scheduled")
    meeting_link = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
