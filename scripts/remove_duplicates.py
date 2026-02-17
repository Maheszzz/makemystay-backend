
import sys
import os
from sqlalchemy import text

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.configs.db_config import get_db
from app.models.realty import Property
from loguru import logger

def remove_recent_duplicates():
    db = next(get_db())
    try:
        # List of duplicate property names obtained from the previous step
        # We want to keep the older versions and remove the newer versions
        # Based on the output:
        # 'DVR Co Living PG Studio Rooms' (ID 59 vs 27) - Remove 59
        # 'AVINYA CO LIVE' vs 'AVINYA Colive' (ID 41 vs 25) - Remove 41
        # 'Haveli coliving pg' vs 'Haveli Coliving' (ID 55 vs 19) - Remove 55
        # 'Arcade Inn...' (ID 46/38 vs 15) - Remove 46, 38
        # 'Connect Coliving' (ID 31/20) - Remove older? No, user said "recently added just rm that"
        # So we remove the ones added on 2026-02-17 (IDs > 32)
        
        # IDs to remove (all from today 2026-02-17)
        # IDs 35 to 63 are all added today.
        # IDs 1 to 32 are older.
        
        # Double check if ALL of them are duplicates or just some.
        # The user said "in propertys rm duplicates that recentely add just rm that"
        # This implies removing the RECENT duplicates.
        # Let's check for visual duplicates based on names.
        
        # Duplicates found:
        # 1. 'Kings & queens colive( B)' (56) vs 'Kings & Queens Coliving' (1)
        # 2. 'Haveli coliving pg' (55) vs 'Haveli Coliving' (19)
        # 3. 'Arcade INN...' (46, 38) vs 'Arcade Inn Coliving' (15)
        # 4. 'AVINYA CO LIVE' (41) vs 'AVINYA Colive' (25)
        # 5. 'DVR Co Living PG Studio Rooms' (59) vs 'DVR Co-Living PG Studio Rooms' (27)
        # 6. 'Connect Coliving 2 ' (31) vs 'Connect coliving' (20) - 31 is older than today, so maybe keep?
        
        # IDs to delete:
        ids_to_delete = [56, 55, 46, 38, 41, 59]
        
        if not ids_to_delete:
            logger.info("No duplicates defined.")
            return

        logger.info(f"Deleting duplicate properties with IDs: {ids_to_delete}")
        
        # Delete properties
        db.query(Property).filter(Property.id.in_(ids_to_delete)).delete(synchronize_session=False)
        db.commit()
        
        logger.success(f"Successfully deleted {len(ids_to_delete)} duplicate properties.")

    except Exception as e:
        logger.error(f"Error removing duplicates: {e}")
        db.rollback()
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    remove_recent_duplicates()
