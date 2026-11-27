
import asyncio
from app.configs.db_config import MySQLSessionLocal
from app.services.lead_sync_service import sync_99acres_leads
from app.core.config import settings

async def force_sync():
    print(f"Current ACRES_API_KEY: {settings.ACRES_API_KEY}")
    if not settings.ACRES_API_KEY:
        print("Error: ACRES_API_KEY is still empty in settings. Reloading .env manually...")
        from dotenv import load_dotenv
        load_dotenv(override=True)
        print(f"Refreshed ACRES_API_KEY: {settings.ACRES_API_KEY}")

    db = MySQLSessionLocal()
    try:
        print("Triggering 99acres sync...")
        await sync_99acres_leads(db)
        print("Sync completed. Checking metadata...")
        from app.models.sync_metadata import SyncMetadata
        meta = db.query(SyncMetadata).filter(SyncMetadata.source == "99acres").first()
        if meta:
            print(f"Status: {meta.status}")
            print(f"Last Error: {meta.last_error}")
            print(f"Leads Fetched: {meta.leads_fetched}")
        else:
            print("No metadata found for 99acres.")
    except Exception as e:
        print(f"Sync failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(force_sync())
