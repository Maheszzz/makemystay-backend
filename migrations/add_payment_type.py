import os
import sys

from sqlalchemy import text

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from app.configs.db_config import mysql_engine


def add_payment_type_column():
    try:
        with mysql_engine.connect() as connection:
            logger.info("Checking if payment_type column exists...")
            result = connection.execute(
                text("SHOW COLUMNS FROM payments LIKE 'payment_type'")
            )
            if result.fetchone():
                logger.info("Column 'payment_type' already exists.")
                return

            logger.info("Adding 'payment_type' column to 'payments' table...")
            connection.execute(
                text(
                    "ALTER TABLE payments ADD COLUMN payment_type VARCHAR(50) NOT NULL DEFAULT 'booking' AFTER currency"
                )
            )
            connection.commit()
            logger.success("Successfully added 'payment_type' column.")

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise e


if __name__ == "__main__":
    add_payment_type_column()
