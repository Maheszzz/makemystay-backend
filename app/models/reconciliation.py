from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from app.configs.db_config import Base

class ReconciliationIssue(Base):
    __tablename__ = "reconciliation_issues"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String(100), nullable=False, index=True)
    issue_type = Column(String(100), nullable=False) # e.g., "missing_payment", "amount_mismatch", "status_mismatch"
    resolved = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
