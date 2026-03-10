import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def add_is_deleted_column():
    try:
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
        )
        db_name = os.getenv("DB_NAME")
        cursor = conn.cursor()
        if db_name:
            cursor.execute(f"USE {db_name}")

        print(f"Using database: {db_name}")
        cursor.execute("SHOW COLUMNS FROM properties LIKE 'is_deleted'")
        if not cursor.fetchone():
            print("Adding is_deleted to properties...")
            cursor.execute(
                "ALTER TABLE properties ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
            )

        print("Checking for is_deleted in property_images table...")
        cursor.execute("SHOW COLUMNS FROM property_images LIKE 'is_deleted'")
        if not cursor.fetchone():
            print("Adding is_deleted to property_images...")
            cursor.execute(
                "ALTER TABLE property_images ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT FALSE"
            )

        conn.commit()
        print("Database schema updated successfully.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    add_is_deleted_column()
