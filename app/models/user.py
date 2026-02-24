from sqlalchemy import Column, Integer, String, DateTime, Enum, func
from app.configs.db_config import MySQLBase

class User(MySQLBase):
    """Model for users table (admin/employee)"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        Enum('admin', 'employee', name='user_role_enum'),
        default='employee',
        nullable=False
    )
    full_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=True)
