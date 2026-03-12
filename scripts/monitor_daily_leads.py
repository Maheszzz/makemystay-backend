import os
import sys
from sqlalchemy import text
from loguru import logger

# Add project root to path
sys.path.append(os.getcwd())

# Force load dotenv
from dotenv import load_dotenv
load_dotenv()

from app.configs.db_config import MySQLSessionLocal

def run_monitoring():
    print("--- 📊 MakeMyStay Lead Flow Monitor ---")
    db = MySQLSessionLocal()
    
    try:
        # 1. Lead Date Volume (Original Inquiries)
        print("\n[Original Lead Date Volume]")
        query_daily = text("""
            SELECT DATE(FROM_UNIXTIME(lead_date)) as date, COUNT(*) as count 
            FROM leads 
            WHERE lead_date IS NOT NULL
            GROUP BY date 
            ORDER BY date DESC 
            LIMIT 10
        """)
        res_daily = db.execute(query_daily).fetchall()
        for r in res_daily:
            print(f"  {r[0]}: {r[1]} leads")

        # 2. Source Breakdown (Today)
        print("\n[Today's Source Breakdown]")
        query_source = text("""
            SELECT source, COUNT(*) as count 
            FROM leads 
            WHERE DATE(created_at) = CURDATE()
            GROUP BY source
        """)
        res_source = db.execute(query_source).fetchall()
        if not res_source:
            print("  No leads recorded today yet.")
        for r in res_source:
            print(f"  {r[0]}: {r[1]}")

        # 3. CRM Parity Check
        print("\n[Zoho CRM Parity Status]")
        query_parity = text("""
            SELECT zoho_synced, COUNT(*) as count
            FROM leads
            GROUP BY zoho_synced
        """)
        res_parity = db.execute(query_parity).fetchall()
        for r in res_parity:
            status = 'Synced' if r[0] else 'Pending'
            print(f"  {status}: {r[1]}")

        # 4. Sync Job Health
        print("\n[Integration Health]")
        query_health = text("SELECT source, status, last_sync_at, last_error FROM sync_metadata")
        res_health = db.execute(query_health).fetchall()
        for r in res_health:
            status_icon = "✅" if r[1] == 'active' else "❌"
            print(f"  {r[0]}: {status_icon} {r[1].upper()}")
            if r[3]:
                print(f"    Last Error: {r[3]}")
    
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_monitoring()
