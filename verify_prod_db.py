import os
import urllib.parse
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load production env explicitly or just use the values we know
# checks .env.production
load_dotenv(".env.production")

DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

print(f"Attempting to connect to {DB_NAME} at {DB_HOST}:{DB_PORT} as {DB_USER}")

encoded_password = urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
MYSQL_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{encoded_password}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

try:
    engine = create_engine(MYSQL_DATABASE_URL, echo=False, pool_pre_ping=True)
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Connection successful! Result:", result.scalar())
        
        # List tables to confirm we are in the right db
        result = connection.execute(text("SHOW TABLES"))
        print("\nTables in database:")
        for row in result:
            print(row[0])
            
except Exception as e:
    print(f"Connection failed: {e}")
