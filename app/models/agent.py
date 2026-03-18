from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class Agent(MySQLBase):
    """Agent model for lead distribution."""

    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False, unique=True, index=True)
    phone = Column(String(20), nullable=False, index=True)
    is_active = Column(Boolean, default=True, index=True)
    current_load = Column(Integer, default=0)
    max_capacity = Column(Integer, default=20)
    location = Column(String(200), nullable=True)
    conversion_rate = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    leads = relationship("Lead", back_populates="agent")
