import requests
import sys

# Get fresh token directly by logging in
login = requests.post("http://localhost:8000/api/v1/auth/login", json={"email": "admin@makemystay.ai", "password": "AdminChangeMe123!"})
if login.status_code != 200:
    print("Login failed", login.status_code, login.text)
    sys.exit(1)
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Attempt to PUT property 82 (if it exists, otherwise we will test with a dummy property)
# We will just GET property 82 to see its data first
get_res = requests.get("http://localhost:8000/api/v1/realty/properties/82")
if get_res.status_code != 200:
    print("Property 82 not found, getting another property for test.")
    all_props = requests.get("http://localhost:8000/api/v1/realty/properties")
    props = all_props.json()
    if not props:
        print("No properties found to test")
        sys.exit(1)
    prop_id = props[0]["id"]
    prop_data = props[0]
else:
    prop_id = 82
    prop_data = get_res.json()

# Prepare payload exactly as PropertyForm does
# Specifically setting some things to empty string to test if it's phone or something else
payload = {
    "property_name": prop_data.get("property_name", ""),
    "location": prop_data.get("location", ""),
    "phone": "",  # Empty string as sent by default state if empty
    "property_type": prop_data.get("property_type", "1BHK"),
    "listing_type": prop_data.get("listing_type", "rent"),
    "furnishing": prop_data.get("furnishing", "semi_furnished"),
    "description": prop_data.get("description", ""),
    "private_price": None,
    "single_price": None,
    "double_price": None,
    "triple_price": None,
    "starting_price": None,
    "is_available": True,
    "features": prop_data.get("features", [])
}

res = requests.put(f"http://localhost:8000/api/v1/realty/properties/{prop_id}", json=payload, headers=headers)
print("PUT status:", res.status_code)
print("PUT response:", res.text)
