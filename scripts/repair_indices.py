import os
import sys
import sqlalchemy as sa
from sqlalchemy import text
from loguru import logger

# Add app directory to path
sys.path.append(os.getcwd())

from app.configs.db_config import MySQLSessionLocal

def repair_indices():
    logger.info("Starting final schema index repair...")
    with MySQLSessionLocal() as session:
        # 1. unique_phone
        try:
            logger.info("Adding unique_phone index...")
            session.execute(text("ALTER TABLE leads ADD UNIQUE INDEX unique_phone (phone);"))
            session.commit()
            logger.success("Added unique_phone index.")
        except Exception as e:
            session.rollback()
            if "Duplicate key name" in str(e):
                logger.info("unique_phone already exists.")
            else:
                logger.error(f"Failed to add unique_phone: {e}")

        # 2. idx_phone_stage
        try:
            logger.info("Adding idx_phone_stage index...")
            # CREATE INDEX doesn't support IF NOT EXISTS in many MySQL versions either
            session.execute(text("CREATE INDEX idx_phone_stage ON leads(phone, lead_stage);"))
            session.commit()
            logger.success("Added idx_phone_stage index.")
        except Exception as e:
            session.rollback()
            if "Duplicate key name" in str(e):
                logger.info("idx_phone_stage already exists.")
            else:
                logger.error(f"Failed to add idx_phone_stage: {e}")

        # 3. unique_normalized_phone
        try:
            logger.info("Adding unique_normalized_phone index...")
            session.execute(text("ALTER TABLE leads ADD UNIQUE INDEX unique_normalized_phone (normalized_phone);"))
            session.commit()
            logger.success("Added unique_normalized_phone index.")
        except Exception as e:
            session.rollback()
            if "Duplicate key name" in str(e):
                logger.info("unique_normalized_phone already exists.")
            else:
                logger.error(f"Failed to add unique_normalized_phone: {e}")

    logger.success("Schema index repair attempt complete.")

if __name__ == "__main__":
    repair_indices()
