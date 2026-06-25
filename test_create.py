import requests

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
    "images": []
}

headers = {
    "Authorization": "Bearer fake_token_just_for_validation_test_or_we_need_a_real_one"
}
# Actually we might need auth to test this. Let's see if we can get a 422 before auth or if auth fails with 401.
res = requests.post("http://localhost:8000/api/v1/realty/properties", json=payload)
print(res.status_code, res.text)
