import requests
import json

url = "http://localhost:8000/api/v1/uploads/presigned-url"
payload = {
    "filename": "test-image.jpg",
    "content_type": "image/jpeg"
}
headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, json=payload, headers=headers)
    if response.status_code == 200:
        print("✅ Success! Presigned URL generated.")
        print(json.dumps(response.json(), indent=2))
    else:
        print(f"❌ Failed. Status: {response.status_code}")
        print(response.text)
except Exception as e:
    print(f"❌ Error: {e}")
