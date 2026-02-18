
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load env
load_dotenv()

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "makemystay")

def main():
    print("--- Debugging Image URLs ---", flush=True)
    print(f"Connecting to {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}", flush=True)
    
    # Construct connection string
    encoded_password = DB_PASSWORD # urllib.parse.quote_plus(DB_PASSWORD) if DB_PASSWORD else ""
    if "@" in encoded_password:
         import urllib.parse
         encoded_password = urllib.parse.quote_plus(encoded_password)

    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{encoded_password}@{DB_HOST}:{int(DB_PORT)}/{DB_NAME}"
    
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            print("Connected!", flush=True)
            result = conn.execute(text("SELECT id, property_name FROM properties LIMIT 5"))
            properties = result.fetchall()
            print(f"Found {len(properties)} properties.", flush=True)
            for p in properties:
                print(f"Property: {p[1]} (ID: {p[0]})", flush=True)
                img_res = conn.execute(text("SELECT image_url, is_primary FROM property_images WHERE property_id = :pid"), {"pid": p[0]})
                images = img_res.fetchall()
                for img in images:
                    print(f"  - Image: {img[0]} (Primary: {img[1]})", flush=True)
                    
    except Exception as e:
        print(f"Error: {e}", flush=True)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
