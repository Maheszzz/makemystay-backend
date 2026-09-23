import asyncio
from app.configs.db_config import SessionLocal
from app.models.realty import Property, PropertyImage

def run():
    db = SessionLocal()
    props = db.query(Property).filter(Property.is_deleted == False).limit(5).all()
    for p in props:
        print(f"Property ID: {p.id}")
        for img in p.images:
            if not img.is_deleted:
                print(f"  Image {img.id} - Primary: {img.is_primary}")

run()
