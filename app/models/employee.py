from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class Employee(MySQLBase):
    """CRM employee (RM) with human-readable code — distinct from auth User."""

    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    employee_id = Column(String(32), nullable=False, unique=True, index=True)  # e.g. EMP001
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=True)
    phone = Column(String(32), nullable=False, server_default=text("''"))
    role = Column(String(80), nullable=False, server_default=text("'RM'"), index=True)
    status = Column(String(32), nullable=False, server_default="active", index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    zoho_user_id = Column(String(100), nullable=True, index=True) # Map to Zoho CRM User ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
        server_default=func.now(),
        onupdate=func.now(),
    )
    created_by = Column(String(100), nullable=True)
    updated_by = Column(String(100), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    user = relationship("User", foreign_keys=[user_id])
    leads = relationship("Lead", back_populates="assigned_employee")
