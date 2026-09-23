import asyncio
from app.configs.db_config import SessionLocal
from app.models.realty import Property

db = SessionLocal()
props = db.query(Property).filter(Property.is_deleted == False).all()
for p in props:
    images = [img for img in p.images if not img.is_deleted]
    if not images: continue
    
    primary_count = sum(1 for img in images if img.is_primary)
    
    if primary_count != 1:
        print(f"Property {p.id} ({p.property_name}): has {len(images)} images, but {primary_count} are primary!")
        for img in images:
            print(f"  Image {img.id} - Primary: {img.is_primary} - URL: {img.image_url}")

