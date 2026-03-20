import json
import hmac
import hashlib
import os

# Set environment variable before importing app
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "test_secret_123"

from fastapi.testclient import TestClient
from app.main import app
from app.configs.db_config import SessionLocal
from app.models.payment import Payment
from app.models.payment_webhook_event import PaymentWebhookEvent


def setup_db():
    db = SessionLocal()
    # Create test payment record
    test_payment = db.query(Payment).filter(Payment.order_id == "order_test_123").first()
    if not test_payment:
        test_payment = Payment(
            order_id="order_test_123",
            amount=500.00,
            currency="INR",
            status="pending",
            payment_type="booking",
            payer_name="Test User",
            payer_email="test@example.com"
        )
        db.add(test_payment)
        db.commit()
        db.refresh(test_payment)
    return db, test_payment

def test_razorpay_webhook():
    print("Setting up test DB...")
    db, test_payment = setup_db()
    
    client = TestClient(app)
    
    payload = {
        "entity": "event",
        "account_id": "acc_123",
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_456",
                    "entity": "payment",
                    "amount": 50000,
                    "currency": "INR",
                    "status": "captured",
                    "order_id": "order_test_123",
                    "method": "upi",
                    "acquirer_data": {
                        "rrn": "31234567890"
                    }
                }
            }
        }
    }
    
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    
    secret = "test_secret_123"
    signature = hmac.new(
        secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Razorpay-Signature": signature,
        "Content-Type": "application/json"
    }

    print("Sending webhook request to /api/v1/payments/webhook")
    response = client.post("/api/v1/payments/webhook", content=payload_bytes, headers=headers)
    
    print(f"Response status: {response.status_code}")
    print(f"Response body: {response.json()}")
    
    # Verify the database was updated
    updated_payment = db.query(Payment).filter(Payment.order_id == "order_test_123").first()
    print(f"DB Payment Status: {updated_payment.status}")
    print(f"DB Payment ID: {updated_payment.payment_id}")
    
    # Check if webhook event was logged
    event = db.query(PaymentWebhookEvent).filter(PaymentWebhookEvent.order_id == "order_test_123").first()
    if event:
        print(f"Webhook logged: Event={event.event}, Status={event.status}")
    else:
        print("Webhook audit event was NOT logged!")

if __name__ == "__main__":
    try:
        test_razorpay_webhook()
    except Exception as e:
        print(f"Error occurred: {e}")
