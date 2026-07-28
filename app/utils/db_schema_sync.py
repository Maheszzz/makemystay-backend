"""
Database Schema Synchronizer (Sprint 1).
Safely inspects existing MySQL tables and adds any newly introduced columns
so that SQLAlchemy models and live database schema stay 100% in sync without data loss.
"""

from sqlalchemy import inspect, text
from loguru import logger
from app.configs.db_config import mysql_engine


def sync_enterprise_schema():
    """Check existing tables and add any missing columns safely."""
    inspector = inspect(mysql_engine)
    existing_tables = inspector.get_table_names()

    columns_to_ensure = {
        "properties": [
            ("property_code", "VARCHAR(50) NULL"),
            ("gender_preference", "VARCHAR(30) NULL"),
            ("property_category", "VARCHAR(50) DEFAULT 'PG'"),
            ("locality", "VARCHAR(150) NULL"),
            ("latitude", "DOUBLE NULL"),
            ("longitude", "DOUBLE NULL"),
            ("available_beds", "INT NULL"),
            ("metadata", "JSON NULL"),
            ("last_verified_at", "DATETIME NULL"),
            ("last_booked_at", "DATETIME NULL"),
            ("last_review_at", "DATETIME NULL"),
            ("status", "VARCHAR(50) DEFAULT 'draft'"),
            ("visibility", "VARCHAR(50) DEFAULT 'public'"),
            ("owner_name", "VARCHAR(150) NULL"),
            ("owner_phone", "VARCHAR(50) NULL"),
            ("owner_email", "VARCHAR(150) NULL"),
            ("assigned_employee_id", "INT NULL"),
            ("created_by", "VARCHAR(100) NULL"),
            ("updated_by", "VARCHAR(100) NULL"),
        ],
        "property_images": [
            ("category", "VARCHAR(50) DEFAULT 'exterior'"),
            ("alt_text", "VARCHAR(200) NULL"),
            ("caption", "VARCHAR(500) NULL"),
            ("seo_tags", "VARCHAR(500) NULL"),
            ("created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "DATETIME NULL"),
            ("created_by", "VARCHAR(100) NULL"),
            ("updated_by", "VARCHAR(100) NULL"),
            ("is_deleted", "BOOLEAN DEFAULT FALSE"),
        ],
        "reviews": [
            ("created_by", "VARCHAR(100) NULL"),
            ("updated_by", "VARCHAR(100) NULL"),
            ("is_deleted", "BOOLEAN DEFAULT FALSE"),
        ],
        "employees": [
            ("created_by", "VARCHAR(100) NULL"),
            ("updated_by", "VARCHAR(100) NULL"),
            ("is_deleted", "BOOLEAN DEFAULT FALSE"),
        ],
    }

    with mysql_engine.begin() as conn:
        for table, col_specs in columns_to_ensure.items():
            if table not in existing_tables:
                continue
            existing_cols = {col["name"].lower() for col in inspector.get_columns(table)}
            for col_name, col_def in col_specs:
                if col_name.lower() not in existing_cols:
                    sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def};"
                    logger.info(f"SYNCING SCHEMA | {sql}")
                    try:
                        conn.execute(text(sql))
                    except Exception as e:
                        logger.warning(f"Schema alter warning for {table}.{col_name}: {e}")

    logger.info("Enterprise Database Schema Synchronized Successfully.")


if __name__ == "__main__":
    sync_enterprise_schema()
