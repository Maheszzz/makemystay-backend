import os
import sys

from sqlalchemy import func

# Add parent directory to path so we can import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from app.configs.db_config import get_db
from app.models.realty import PropertyImage


def remove_duplicate_images():
    db = next(get_db())
    try:
        logger.info("Starting duplicate image removal...")

        # 1. Find duplicates: (property_id, image_url) groups having count > 1
        duplicates_query = (
            db.query(
                PropertyImage.property_id,
                PropertyImage.image_url,
                func.count(PropertyImage.id).label("count"),
            )
            .group_by(PropertyImage.property_id, PropertyImage.image_url)
            .having(func.count(PropertyImage.id) > 1)
            .all()
        )

        if not duplicates_query:
            logger.info("✅ No duplicate images found.")
            return

        logger.info(f"Found {len(duplicates_query)} groups of duplicate images.")

        total_deleted = 0

        for prop_id, img_url, count in duplicates_query:
            # 2. For each duplicate group, get all IDs ordered by ID ASC
            images = (
                db.query(PropertyImage)
                .filter(
                    PropertyImage.property_id == prop_id,
                    PropertyImage.image_url == img_url,
                )
                .order_by(PropertyImage.id.asc())
                .all()
            )

            # Keep the first one (original), delete the rest
            original = images[0]
            duplicates = images[1:]

            duplicate_ids = [img.id for img in duplicates]
            logger.info(
                f"  Property {prop_id}: Keeping ID {original.id}, deleting IDs {duplicate_ids} (URL: {img_url[:30]}...)"
            )

            # 3. Delete
            db.query(PropertyImage).filter(PropertyImage.id.in_(duplicate_ids)).delete(
                synchronize_session=False
            )
            total_deleted += len(duplicate_ids)

        db.commit()
        logger.success(
            f"✅ Successfully deleted {total_deleted} duplicate image records."
        )

    except Exception as e:
        logger.error(f"❌ Error removing duplicates: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    remove_duplicate_images()
