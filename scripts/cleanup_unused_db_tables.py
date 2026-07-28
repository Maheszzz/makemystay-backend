#!/usr/bin/env python3
"""
Cleanup unused tables, Zoho CRM tables, and legacy Leads tables from MakeMyStay MySQL Database.
"""

import os
import sys
from sqlalchemy import inspect, text
from loguru import logger

# Add root directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.configs.db_config import mysql_engine


TABLES_TO_DROP = [
    "zoho_webhook_events",
    "failed_zoho_tasks",
    "lead_events",
    "lead_activities",
    "lead_assignments",
    "failed_webhook_leads",
    "csv_import_failures",
    "csv_imports",
    "retell_calls",
    "demo_bookings",
    "failed_jobs",
    "sync_jobs",
    "sync_metadata",
    "reconciliation_issues",
    "agents",
    "assignment_batches",
    "leads",
]


def cleanup_db():
    logger.info("Starting cleanup of unused, Zoho, and legacy Leads tables...")

    with mysql_engine.begin() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        # 1. Ensure property_leads has name, phone, email columns and backfill before dropping leads
        if "property_leads" in existing_tables and "leads" in existing_tables:
            logger.info("Checking property_leads columns...")
            cols = {col["name"] for col in inspector.get_columns("property_leads")}
            if "name" not in cols:
                conn.execute(text("ALTER TABLE property_leads ADD COLUMN name VARCHAR(200) NULL;"))
            if "phone" not in cols:
                conn.execute(text("ALTER TABLE property_leads ADD COLUMN phone VARCHAR(50) NULL;"))
            if "email" not in cols:
                conn.execute(text("ALTER TABLE property_leads ADD COLUMN email VARCHAR(150) NULL;"))

            # Backfill
            logger.info("Backfilling property_leads from leads...")
            conn.execute(text("""
                UPDATE property_leads pl
                JOIN leads l ON pl.lead_id = l.id
                SET pl.name = l.name, pl.phone = l.phone, pl.email = l.email
                WHERE pl.lead_id IS NOT NULL;
            """))

            # Check if foreign key property_leads_ibfk_2 exists and drop it
            fks = {fk["name"] for fk in inspector.get_foreign_keys("property_leads") if fk.get("name")}
            if "property_leads_ibfk_2" in fks:
                logger.info("Dropping foreign key property_leads_ibfk_2 from property_leads...")
                conn.execute(text("ALTER TABLE property_leads DROP FOREIGN KEY property_leads_ibfk_2;"))

        # 2. Drop unused / zoho / legacy leads tables
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        for table in TABLES_TO_DROP:
            if table in existing_tables:
                logger.info(f"Dropping table: {table} ...")
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table};"))
                    logger.info(f"Successfully dropped {table}.")
                except Exception as e:
                    logger.error(f"Error dropping {table}: {e}")
            else:
                logger.info(f"Table {table} does not exist, skipping.")
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))

    # Verify remaining tables
    inspector = inspect(mysql_engine)
    remaining_tables = inspector.get_table_names()
    logger.info(f"Cleanup complete! Remaining tables in database ({len(remaining_tables)}): {sorted(remaining_tables)}")


if __name__ == "__main__":
    cleanup_db()
