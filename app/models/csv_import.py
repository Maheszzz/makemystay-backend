from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.configs.db_config import MySQLBase


class CsvImport(MySQLBase):
    """Tracks history of manual lead imports from CSV."""

    __tablename__ = "csv_imports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=True, index=True)  # MD5 for idempotency
    source = Column(String(100), nullable=False)
    total_rows = Column(Integer, default=0)
    imported = Column(Integer, default=0)
    duplicates = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped_no_phone = Column(Integer, default=0)
    
    # Automation Controls
    sync_to_zoho = Column(Boolean, default=True)
    send_whatsapp = Column(Boolean, default=True)
    trigger_ai = Column(Boolean, default=True)

    status = Column(
        String(32), default="pending", index=True
    )  # pending, processing, completed, partial, failed, cancelled
    processing_started_at = Column(DateTime(timezone=True), nullable=True)
    processing_completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float(), nullable=True)
    rows_per_second = Column(Float(), nullable=True)
    failure_rate = Column(Float(), nullable=True)
    success_rate = Column(Float(), nullable=True)
    avg_row_latency_ms = Column(Float(), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("User")
    failures = relationship("CsvImportFailure", back_populates="import_record", cascade="all, delete-orphan")


class CsvImportFailure(MySQLBase):
    """Tracks individual row failures within a CSV import for debugging/retry."""
    __tablename__ = "csv_import_failures"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    import_id = Column(Integer, ForeignKey("csv_imports.id"), nullable=False, index=True)
    row_index = Column(Integer, nullable=True)  # Line number in CSV
    row_data = Column(JSON, nullable=False)    # Exact JSON data that failed
    error_message = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    import_record = relationship("CsvImport", back_populates="failures")
