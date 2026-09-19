from app.configs.db_config import SessionLocal
from app.models.realty import Property

db = SessionLocal()
p = db.query(Property).filter(Property.slug == "cozy-homes").first()
print("Found by slug:", p)
