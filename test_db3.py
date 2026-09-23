import requests
from app.configs.db_config import SessionLocal
from app.models.realty import Property

db = SessionLocal()
prop = db.query(Property).filter(Property.id == 361).first()
if not prop: exit(0)

payload = {
    "property_name": prop.property_name,
    "images": []
}

images = [img for img in prop.images if not img.is_deleted]
for idx, img in enumerate(images):
    # Let's set the first one to False, and the last one to True
    payload["images"].append({
        "id": img.id,
        "image_url": img.image_url,
        "is_primary": idx == len(images) - 1,
        "sort_order": idx
    })

resp = requests.put("http://localhost:8000/api/v1/realty/properties/361", json=payload)
print(resp.status_code)
print(resp.json())

db.expire_all()
prop = db.query(Property).filter(Property.id == 361).first()
images = [img for img in prop.images if not img.is_deleted]
for img in images:
    print(f"  Image {img.id} - Primary: {img.is_primary}")

