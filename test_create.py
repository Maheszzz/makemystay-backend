import requests
import json

payload = {
    "property_name": "Test Property",
    "property_type": "PG",
    "listing_type": "rent",
    "category": "pg",
    "city": "Bangalore",
    "location": "HSR Layout",
    "starting_price": 15000,
    "is_available": True,
    "features": [],
    "metadata": {
        "property_status": "Available",
        "is_featured": False,
        "is_high_demand": False,
        "negotiable": True,
        "brokerage": "0 (No Brokerage)",
        "uploaded_images": [],
        "nearby_places": []
    }
}

try:
    res = requests.post("http://localhost:8000/api/v1/realty/properties", json=payload)
    print("Status:", res.status_code)
    print("Response:", res.text)
except Exception as e:
    print(e)
