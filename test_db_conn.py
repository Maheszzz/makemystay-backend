import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

print(f"Testing connection to {os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}...")

try:
    conn = pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        connect_timeout=5
    )
    print("✅ Successfully connected to the database!")
    
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print("Tables found:")
        for table in tables:
            print(f" - {table[0]}")
            
    conn.close()
except Exception as e:
    print(f"❌ Connection failed: {e}")
