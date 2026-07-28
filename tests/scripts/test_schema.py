import sys
from app.schemas.realty import PropertyCreate

payload = {
    "property_name": "Test Property",
    "property_type": "PG",
    "listing_type": "rent",
    "category": "pg",
    "city": "bangalore",
    "is_available": True,
    "features": [],
    "metadata": {},
    "location": "Test Location",
    "phone": "9876543210",
    "starting_price": 5000,
    "images": [{"url": "foo"}],
    "lift": True
}
try:
    p = PropertyCreate(**payload)
    print("Success")
except Exception as e:
    print(e)
