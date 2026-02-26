import subprocess
import requests
import sys

# Get fresh token directly by logging in
login = requests.post("http://localhost:8000/api/v1/admin/login", data={"username": "admin", "password": "password"})
if login.status_code != 200:
    print("Login failed", login.text)
    sys.exit(1)
token = login.json()["access_token"]

headers = {"Authorization": f"Bearer {token}"}
payload = {"image_url": "https://xyz.com/image.jpg", "is_primary": False, "sort_order": 0}
res = requests.post("http://localhost:8000/api/v1/realty/properties/77/images", json=payload, headers=headers)
print(res.status_code, res.text)
