from app.configs.db_config import mysql_engine
from sqlalchemy import text

def insert_users():
    with mysql_engine.connect() as conn:
        conn.execute(text("USE makemystay;"))
        conn.execute(text("""
        INSERT INTO retell_call_tests (name, to_phone, status) VALUES
        ('Test 1', '+919790341157', 'queued'),
        ('Test 2', '+919944715881', 'queued'),
        ('Test 3', '+919706107145', 'queued'),
        ('Test 4', '+918248931176', 'queued')
        ON DUPLICATE KEY UPDATE name=VALUES(name);
        """))
        conn.commit()
    print("Inserted users successfully.")

if __name__ == "__main__":
    insert_users()
