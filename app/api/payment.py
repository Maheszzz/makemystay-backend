import os
import razorpay
import hashlib
import hmac
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from app.schemas.payment import ServiceFeeValidationRequest, ValidationResponse, PaymentInitiationRequest, PaymentResponse
from app.configs.db_config import get_db
from app.models.payment import Payment
from loguru import logger
from pydantic import BaseModel

router = APIRouter()

# Initialize Razorpay client
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

class CreateOrderRequest(BaseModel):
    amount: int  # in paise
    currency: str = "INR"
    payment_type: str = "booking"
    payer_name: Optional[str] = None
    payer_email: Optional[str] = None
    payer_phone: Optional[str] = None

@router.post("/payments/validate-fee", response_model=ValidationResponse)
def validate_service_fee(data: ServiceFeeValidationRequest):
    logger.info(f"Validating fee for property {data.property_id} ({data.property_type})")
    
    prop_type = data.property_type.upper()
    fee = data.service_fee_amount
    fee_type = data.service_fee_type

    is_valid = False
    message = "Invalid service fee configuration"

    if prop_type in ['PG', 'COLIVE PG']:
        if fee_type == 'sharing' and fee == 1500:
            is_valid = True
            message = "Valid Sharing PG Fee"
        elif fee_type == 'private' and fee == 2500:
            is_valid = True
            message = "Valid Private PG Fee"
        else:
            message = "Invalid fee for PG. Expected 1500 (Sharing) or 2500 (Private)."

    elif prop_type == '1BHK':
        if fee == 4000:
            is_valid = True
            message = "Valid 1BHK Fee"
        else:
            message = "Invalid fee for 1BHK. Expected 4000."
            
    elif prop_type == '2BHK':
        if fee == 6000:
            is_valid = True
            message = "Valid 2BHK Fee"
        else:
            message = "Invalid fee for 2BHK. Expected 6000."
    
    else:
        # Fallback or other types validation
        if fee > 0:
            is_valid = True
            message = "Fee accepted for other property types"

    if not is_valid:
        raise HTTPException(status_code=400, detail=message)

    return {"valid": is_valid, "message": message}


@router.post("/payments/create-order")
def create_order(data: CreateOrderRequest, db: Session = Depends(get_db)):
    try:
        data_dict = {
            "amount": data.amount,
            "currency": data.currency,
            "payment_capture": 1
        }
        order = client.order.create(data_dict)
        
        # Save to DB
        db_payment = Payment(
            amount=data.amount / 100,  # Store in rupees
            currency=data.currency,
            payment_type=data.payment_type,
            status='pending',
            order_id=order['id'],
            payer_name=data.payer_name,
            payer_email=data.payer_email,
            payer_phone=data.payer_phone
        )
        db.add(db_payment)
        db.commit()
        db.refresh(db_payment)
        
        return order
    except Exception as e:
        logger.error(f"Error creating Razorpay order: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payments/verify")
async def verify_payment(req: Request, db: Session = Depends(get_db)):
    body = await req.json()
    
    razorpay_order_id = body.get("razorpay_order_id")
    razorpay_payment_id = body.get("razorpay_payment_id")
    razorpay_signature = body.get("razorpay_signature")
    
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
         raise HTTPException(status_code=400, detail="Missing payment details")

    try:
        # Verify signature
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature
        })
        
        # Update DB
        payment = db.query(Payment).filter(Payment.order_id == razorpay_order_id).first()
        if payment:
            payment.status = 'success'
            payment.payment_id = razorpay_payment_id
            payment.signature = razorpay_signature
            db.commit()
            
        return {"status": "success"}
    except razorpay.errors.SignatureVerificationError:
        # Update DB to failed if possible
        payment = db.query(Payment).filter(Payment.order_id == razorpay_order_id).first()
        if payment:
            payment.status = 'failed'
            payment.payment_id = razorpay_payment_id
            payment.signature = razorpay_signature
            db.commit()
            
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
