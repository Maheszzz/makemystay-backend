import asyncio
from typing import Dict, Any
import httpx
from datetime import datetime
from app.configs.db_config import SessionLocal
from app.models.payment import Payment
from app.api.payment import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

db = SessionLocal()

def extract_bank_rrn(acquirer_data: Dict[str, Any]) -> str:
    if not acquirer_data: return ""
    for key in ["rrn", "upi_transaction_id", "bank_transaction_id", "bank_ref_num", "arn"]:
        if val := acquirer_data.get(key):
            return str(val)
    return ""

def recover_payments():
    with httpx.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) as client:
        # Fetch last 50 payments directly from Razorpay
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
            new_payment = Payment(
                status="success" if p.get("status") == "captured" else "failed" if p.get("status") == "failed" else "pending",
                payment_id=pay_id,
                amount=amount_int / 100,
                currency=p.get("currency", "INR"),
                payment_type="external_link_recovery",
                payer_email=p.get("email"),
                payer_phone=p.get("contact"),
            )
            notes = p.get("notes") or {}
            if name := notes.get("name"):
                new_payment.payer_name = name
            
            db.add(new_payment)
            db.commit()
            imported += 1
            print(f"Recovered missing payment: {pay_id} ({amount_int/100} INR)")
            
        print(f"Total Recovered: {imported}. Skipped (already in DB): {skipped}.")

if __name__ == "__main__":
    recover_payments()
