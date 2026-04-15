import os
import sys

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.configs.db_config import SessionLocal
from app.models.realty import Property
from app.repo.realty import generate_unique_slug


def backfill_slugs():
    db = SessionLocal()
    try:
        properties = (
            db.query(Property)
            .filter((Property.slug == None) | (Property.slug == ""))
            .all()
        )

        count = 0
        for p in properties:
            if p.property_name:
                slug = generate_unique_slug(
                    db,
                    p.property_name,
                    p.property_type,
                    p.location,
                )
                p.slug = slug
                count += 1

        db.commit()
        print(f"Successfully generated offline slugs for {count} properties.")

    except Exception as e:
        db.rollback()
        print(f"Error during backfill: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting slug backfill process...")
    backfill_slugs()
