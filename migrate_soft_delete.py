from app.configs.db_config import MySQLSessionLocal
from app.models.realty import Property, PropertyImage


def migrate_soft_delete():
    db = MySQLSessionLocal()
    try:
        # Update existing properties
        db.query(Property).update({Property.is_deleted: False})
        # Update existing images
        db.query(PropertyImage).update({PropertyImage.is_deleted: False})
        db.commit()
        print("Successfully migrated soft delete columns.")
    except Exception as e:
        print(f"Error migrating: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    migrate_soft_delete()
