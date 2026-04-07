import os
import sys

# Add the app directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.configs.db_config import MySQLSessionLocal
from app.repo.realty import refresh_property_review_stats
from app.models.realty import Property

def main():
    db = MySQLSessionLocal()
    try:
        properties = db.query(Property).all()
        print(f"Found {len(properties)} properties.")
        for prop in properties:
            print(f"Refreshing stats for property: {prop.property_name} (ID: {prop.id})")
            refresh_property_review_stats(db, prop.id)
        print("Done.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
