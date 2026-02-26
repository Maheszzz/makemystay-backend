import requests
import sys

# Get fresh token directly by logging in
login = requests.post("http://localhost:8000/api/v1/auth/login", json={"email": "admin@makemystay.ai", "password": "AdminChangeMe123!"})
if login.status_code != 200:
    print("Login failed", login.status_code, login.text)
    sys.exit(1)
token = login.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# We will GET property 82 to see its data first
get_res = requests.get("http://localhost:8000/api/v1/realty/properties/82")
if get_res.status_code != 200:
    print("Property 82 not found")
    sys.exit(1)

prop_data = get_res.json()

# Prepare payload exactly as PropertyForm does after "cleanPayload" mapping
payload = {
    "property_name": prop_data.get("property_name", ""),
    "location": prop_data.get("location", ""),
    "phone": prop_data.get("phone") or None,
    "property_type": prop_data.get("property_type", "1BHK"),
    "listing_type": prop_data.get("listing_type", "rent"),
    "furnishing": prop_data.get("furnishing", "semi_furnished"),
    "description": prop_data.get("description") or None,
    "private_price": prop_data.get("private_price"),
    "single_price": prop_data.get("single_price"),
    "double_price": prop_data.get("double_price"),
    "triple_price": prop_data.get("triple_price"),
    "starting_price": prop_data.get("starting_price"),
    "is_available": True,
    "features": prop_data.get("features", [])
}

# In frontend form, undefined fields might just not be included or be set to empty strings.
# But since we use `prop_data`, they might just be missing. Let's explicitly set what would be sent:
# Let's test with the payload!
for k, v in list(payload.items()):
    if v == "":
        payload[k] = None

res = requests.put("http://localhost:8000/api/v1/realty/properties/82", json=payload, headers=headers)
print("PUT status:", res.status_code)
print("PUT response:", res.text)
