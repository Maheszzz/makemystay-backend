import asyncio
from app.configs.db_config import SessionLocal
from app.models.payment_webhook_event import PaymentWebhookEvent
db = SessionLocal()
events = db.query(PaymentWebhookEvent).filter(PaymentWebhookEvent.reason == 'payment_not_found').order_by(PaymentWebhookEvent.created_at.desc()).limit(5).all()
for e in events:
    print(f"[{e.created_at}] Event: {e.event}, order: {e.order_id}, pay: {e.payment_id}")
