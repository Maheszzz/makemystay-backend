import httpx
import sys
import os
from dotenv import load_dotenv

load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

print(f"Key ID: {RAZORPAY_KEY_ID}")

data_dict = {
    "amount": 500000,
    "currency": "INR",
    "payment_capture": 1,
}

try:
    with httpx.Client(timeout=10.0, auth=(RAZORPAY_KEY_ID or "", RAZORPAY_KEY_SECRET or "")) as http:
        resp = http.post(
            "https://api.razorpay.com/v1/orders",
            json=data_dict,
        )
        resp.raise_for_status()
        print(resp.json())
except httpx.HTTPStatusError as e:
    print(f"HTTPStatusError: {e.response.status_code}")
    print(f"Response text: {e.response.text}")
except Exception as e:
    print(f"Error: {e}")
