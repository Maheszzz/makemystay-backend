import asyncio
from app.configs.db_config import SessionLocal
from app.models.realty import Property
from app.repo.realty import update_property
from sqlalchemy.orm import Session

db = SessionLocal()
prop = db.query(Property).filter(Property.is_deleted == False).first()
if not prop:
    print("No property found")
    exit(0)

existing_images = {img.id: img for img in prop.images if not img.is_deleted}
print("Before update:")
for img_id, img in existing_images.items():
    print(f"  Image {img_id} - Primary: {img.is_primary}")

images_data = []
# Pick the last image to be primary
has_primary = False
for idx, (img_id, img) in enumerate(existing_images.items()):
    is_primary = False
    if idx == len(existing_images) - 1:
        is_primary = True
    images_data.append({
        "id": img_id,
        "is_primary": is_primary,
        "sort_order": idx,
        "image_url": img.image_url
    })

# The actual logic in API
incoming_ids = []
deleted_ids = []
has_primary = False
for idx, img_data in enumerate(images_data):
    img_id = img_data.get("id")
    is_primary = img_data.get("is_primary", False)
    if is_primary:
        if has_primary:
            is_primary = False
        else:
            has_primary = True
    sort_order = img_data.get("sort_order", idx)
    image_url = img_data.get("image_url")
    if img_id in existing_images:
        existing_img = existing_images[img_id]
        existing_img.is_primary = is_primary
        existing_img.sort_order = sort_order
        existing_img.image_url = image_url
        incoming_ids.append(img_id)

db.commit()
db.refresh(prop)

print("\nAfter update:")
for img in prop.images:
    if not img.is_deleted:
        print(f"  Image {img.id} - Primary: {img.is_primary}")

