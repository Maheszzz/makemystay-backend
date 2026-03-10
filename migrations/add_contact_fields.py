import os
import sys

from sqlalchemy import text

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from app.configs.db_config import mysql_engine


def add_contact_fields():
    try:
        with mysql_engine.connect() as connection:
            logger.info(
                "Adding location and property_type columns to contacts table..."
            )

            # Check if columns already exist
            result = connection.execute(
                text(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_NAME = 'contacts' AND COLUMN_NAME IN ('location', 'property_type')"
                )
            )
            existing_columns = [row[0] for row in result.fetchall()]

            if "location" not in existing_columns:
                logger.info("Adding 'location' column...")
                connection.execute(
                    text("ALTER TABLE contacts ADD COLUMN location VARCHAR(100) NULL")
                )
            else:
                logger.info("'location' column already exists.")

            if "property_type" not in existing_columns:
                logger.info("Adding 'property_type' column...")
                connection.execute(
                    text(
                        "ALTER TABLE contacts ADD COLUMN property_type VARCHAR(50) NULL"
                    )
                )
            else:
                logger.info("'property_type' column already exists.")

            connection.commit()
            logger.success("Successfully added contact fields to database.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise e


if __name__ == "__main__":
    add_contact_fields()
