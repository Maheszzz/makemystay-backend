import os
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

# Try to load from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

user = os.getenv("DB_USER", "appuser")
password = os.getenv("DB_PASSWORD", "StrongPassword@123")
host = os.getenv("DB_HOST", "127.0.0.1")
port = os.getenv("DB_PORT", "3336")
name = os.getenv("DB_NAME", "makemystay")

encoded_password = quote_plus(password)
url = f"mysql+pymysql://{user}:{encoded_password}@{host}:{port}/{name}"

try:
    engine = create_engine(url)
    with engine.connect() as conn:
        print("\n--- Duplicate Leads Check ---")
        dup_result = conn.execute(text("""
            SELECT phone, COUNT(*) as count 
            FROM leads 
            WHERE is_deleted = 0
            GROUP BY phone 
            HAVING count > 1
            ORDER BY count DESC 
            LIMIT 20
        """))
        print(f"{'Phone':<20} | {'Count'}")
        print("-" * 30)
        for row in dup_result:
            print(f"{str(row[0]):<20} | {row[1]}")

        print("\n--- CRM Sync Status Check ---")
        crm_result = conn.execute(text("""
            SELECT crm_status, COUNT(*) 
            FROM leads 
            WHERE is_deleted = 0
            GROUP BY crm_status
        """))
        print(f"{'CRM Status':<20} | {'Count'}")
        print("-" * 30)
        for row in crm_result:
            print(f"{str(row[0]):<20} | {row[1]}")
            
except Exception as e:
    print(f"Error: {e}")
