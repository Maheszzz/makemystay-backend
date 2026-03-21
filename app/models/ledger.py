from sqlalchemy import Column, Integer, String, DateTime, func, CheckConstraint
from app.configs.db_config import Base

class LedgerEntry(Base):
    __tablename__ = "ledger"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String(100), nullable=False, index=True)
    entry_type = Column(String(50), nullable=False) # e.g., "credit", "refund"
    amount = Column(Integer, nullable=False)        # Store in cents or smallest currency unit ideally, but matching whatever `payments` table uses
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(entry_type.in_(['credit', 'refund']), name='valid_ledger_entry_type'),
    )
