import sys
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
        result = conn.execute(text("""
            SELECT 
                source, 
                status, 
                FROM_UNIXTIME(last_lead_timestamp) as last_lead_time, 
                last_sync_at, 
                leads_fetched, 
                last_error 
            FROM sync_metadata
        """))
        print(f"{'Source':<15} | {'Status':<10} | {'Last Lead Time':<20} | {'Last Sync At':<20} | {'Fetched':<10} | {'Error'}")
        print("-" * 110)
        for row in result:
            print(f"{str(row[0]):<15} | {str(row[1]):<10} | {str(row[2]):<20} | {str(row[3]):<20} | {str(row[4]):<10} | {str(row[5])}")
except Exception as e:
    print(f"Error: {e}")
