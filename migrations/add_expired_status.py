import sys
import os
from sqlalchemy import text

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.configs.db_config import mysql_engine
from loguru import logger

def add_expired_status():
    try:
        with mysql_engine.connect() as connection:
            logger.info("Adding 'expired' status to payment_status_enum...")
            
            # Check current enum values
            result = connection.execute(text(
                "SELECT COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = 'payments' AND COLUMN_NAME = 'status'"
            ))
            current_type = result.fetchone()[0]
            logger.info(f"Current enum type: {current_type}")
            
            # Check if 'expired' already exists
            if 'expired' in current_type:
                logger.info("Status 'expired' already exists in enum.")
                return
            
            # Alter the enum to add 'expired'
            connection.execute(text(
                "ALTER TABLE payments MODIFY COLUMN status "
                "ENUM('pending', 'success', 'failed', 'expired') "
                "DEFAULT 'pending' NOT NULL"
            ))
            connection.commit()
            logger.success("Successfully added 'expired' status to payment_status_enum.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise e

if __name__ == "__main__":
    add_expired_status()
