from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class AssignmentBatch(MySQLBase):
    __tablename__ = "assignment_batches"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    total_leads = Column(Integer, nullable=False)
    rm_count = Column(Integer, nullable=False)
    strategy = Column(
        Enum("round_robin", "load_balanced", "manual_bulk", name="assign_strategy_enum"),
        nullable=False,
    )
    distribution = Column(JSON, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    creator = relationship("User", foreign_keys=[created_by])
