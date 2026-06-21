from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func
from app.configs.db_config import Base

class WhatsAppLead(Base):
    __tablename__ = "whatsapp_leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    phone = Column(String(20), index=True, nullable=False)
    email = Column(String(200), nullable=True)
    preferred_location = Column(String(200), nullable=True)
    property_type = Column(String(100), nullable=True)
    message = Column(Text, nullable=True)
    source = Column(String(100), default="Website - WhatsApp Widget")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
