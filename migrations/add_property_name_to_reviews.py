import sys
import os
from sqlalchemy import text

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.configs.db_config import mysql_engine
from loguru import logger

def migrate_reviews_property_name():
    try:
        with mysql_engine.connect() as connection:
            logger.info("Checking for 'property_name' column in 'reviews' table...")
            
            # Check if column already exists
            result = connection.execute(text(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = 'reviews' AND COLUMN_NAME = 'property_name'"
            ))
            exists = result.fetchone()
            
            if not exists:
                logger.info("Adding 'property_name' column to 'reviews' table...")
                connection.execute(text("ALTER TABLE reviews ADD COLUMN property_name VARCHAR(150) NULL AFTER user_name"))
                logger.info("Successfully added 'property_name' column.")
            else:
                logger.info("'property_name' column already exists.")

            logger.info("Backfilling 'property_name' for existing reviews...")
            # Update reviews by joining with properties table
            update_query = text("""
                UPDATE reviews r
                JOIN properties p ON r.property_id = p.id
                SET r.property_name = p.property_name
                WHERE r.property_name IS NULL
            """)
            result = connection.execute(update_query)
            logger.info(f"Backfilled property_name for {result.rowcount} records.")
            
            connection.commit()
            logger.success("Migration and backfill completed successfully.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise e

if __name__ == "__main__":
    migrate_reviews_property_name()
