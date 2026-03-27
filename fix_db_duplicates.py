import traceback
from sqlalchemy import text
from app.configs.db_config import MySQLSessionLocal
from loguru import logger

def clean_duplicates_and_add_constraint():
    logger.info("Starting database cleanup for leads...")
    try:
        with MySQLSessionLocal() as session:
            # Drop constraint if it already exists (to avoid errors if run multiple times)
            try:
                session.execute(text("ALTER TABLE leads DROP INDEX unique_phone;"))
                session.commit()
                logger.info("Dropped existing unique_phone constraint to recreate it safely.")
            except Exception as e:
                session.rollback()
                logger.info("No existing unique_phone constraint found or couldn't drop.")

            # Find all min IDs per phone
            logger.info("Cleaning up duplicate lead entries keeping only the oldest record per phone...")
            delete_sql = """
            DELETE l1 FROM leads l1 
            INNER JOIN leads l2 
            WHERE l1.id > l2.id AND l1.phone = l2.phone;
            """
            session.execute(text(delete_sql))
            session.commit()
            logger.info("Duplicate leads cleaned successfully.")

            logger.info("Adding unique constraint on phone column...")
            alter_sql = """
            ALTER TABLE leads ADD CONSTRAINT unique_phone UNIQUE (phone);
            """
            session.execute(text(alter_sql))
            session.commit()
            logger.info("Unique constraint on phone added successfully.")
            
    except Exception as e:
        logger.error(f"Error executing DB script: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    clean_duplicates_and_add_constraint()
