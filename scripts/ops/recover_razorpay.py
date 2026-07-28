import os
from datetime import datetime, timezone
import httpx

from app.configs.db_config import SessionLocal

# Force evaluation of all models to resolve Mapper relationships
import app.models.user
import app.models.realty
import app.models.booking
import app.models.payment

from app.models.payment import Payment
from app.api.payment import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

def recover_payments():
    db = SessionLocal()
    try:
        print("Connecting to Razorpay...")
        with httpx.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) as client:
            res = client.get("https://api.razorpay.com/v1/payments", params={"count": 50})
            res.raise_for_status()
            items = res.json().get("items", [])
            
            imported = 0
            skipped = 0
            for p in items:
                pay_id = p.get("id")
                if db.query(Payment).filter(Payment.payment_id == pay_id).first():
                    skipped += 1
                    continue
                    
                amount_int = int(p.get("amount", 0))
                
                # Payment notes handling
                notes = p.get("notes") or {}
                name = notes.get("name") if isinstance(notes, dict) else None
                
                # Status mapping
                raw_stat = p.get("status")
                stat = "success" if raw_stat in ["captured", "paid"] else "failed" if raw_stat == "failed" else "pending"
                
                safe_order_id = p.get("order_id")
                if not safe_order_id:
                    safe_order_id = f"ext_{pay_id}"
                
                new_payment = Payment(
                    status=stat,
                    order_id=safe_order_id,
                    payment_id=pay_id,
                    amount=amount_int / 100,
                    currency=p.get("currency", "INR"),
                    payment_type="external_link_recovery",
                    payer_email=p.get("email"),
                    payer_phone=p.get("contact"),
                    payer_name=name
                )
                
                # Created timestamp if available
                created = p.get("created_at")
                if isinstance(created, int):
                    new_payment.created_at = datetime.fromtimestamp(created, tz=timezone.utc)
                
                db.add(new_payment)
                db.commit()
                imported += 1
                currency = p.get("currency", "INR")
                print(f"Recovered: {pay_id} | {amount_int/100} {currency} | {p.get('contact')}")
                
            print(f"Recovery complete. Imported {imported} missing external payments. Skipped {skipped}.")
    except Exception as e:
        print(f"Error recovering payments: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    recover_payments()
