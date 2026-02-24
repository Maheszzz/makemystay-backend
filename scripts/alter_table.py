import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from app.configs.db_config import mysql_engine

def add_slug_column():
    try:
        with mysql_engine.connect() as conn:
            # Check if column exists first to avoid errors
            result = conn.execute(text("SHOW COLUMNS FROM properties LIKE 'slug'"))
            if result.fetchone() is None:
                print("Adding slug column to properties table...")
                conn.execute(text("ALTER TABLE properties ADD COLUMN slug VARCHAR(200) UNIQUE DEFAULT NULL"))
                conn.commit()
                print("Successfully added slug column.")
            else:
                print("Slug column already exists.")
    except Exception as e:
        print(f"Error altering table: {e}")

if __name__ == "__main__":
    add_slug_column()
