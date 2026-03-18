import base64
import os
from datetime import datetime
from io import BytesIO
from typing import List, Optional

import jinja2
import qrcode
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.configs.db_config import get_db, get_mysql_db
from app.core.config import settings
from app.models.payment import Payment
from app.schemas.payment import (
    PaymentSchema,
    ServiceFeeValidationRequest,
    ValidationResponse,
)

router = APIRouter()

# Initialize Razorpay client
RAZORPAY_KEY_ID = settings.RAZORPAY_KEY_ID
RAZORPAY_KEY_SECRET = settings.RAZORPAY_KEY_SECRET

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
    logger.info(
        f"Validating fee for property {data.property_id} ({data.property_type})"
    )

    prop_type = data.property_type.upper()
    fee = data.service_fee_amount
    fee_type = data.service_fee_type

    is_valid = False
    message = "Invalid service fee configuration"

    if prop_type in ["PG", "COLIVE PG"]:
        if fee_type == "sharing" and fee == 1500:
            is_valid = True
            message = "Valid Sharing PG Fee"
        elif fee_type == "private" and fee == 2500:
            is_valid = True
            message = "Valid Private PG Fee"
        else:
            message = "Invalid fee for PG. Expected 1500 (Sharing) or 2500 (Private)."

    elif prop_type == "1BHK":
        if fee == 4000:
            is_valid = True
            message = "Valid 1BHK Fee"
        else:
            message = "Invalid fee for 1BHK. Expected 4000."

    elif prop_type == "2BHK":
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
            "payment_capture": 1,
        }
        order = client.order.create(data_dict)

        # Save to DB
        db_payment = Payment(
            amount=data.amount / 100,  # Store in rupees
            currency=data.currency,
            payment_type=data.payment_type,
            status="pending",
            order_id=order["id"],
            payer_name=data.payer_name,
            payer_email=data.payer_email,
            payer_phone=data.payer_phone,
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
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            }
        )

        # Update DB
        payment = (
            db.query(Payment).filter(Payment.order_id == razorpay_order_id).first()
        )
        if payment:
            payment.status = "success"
            payment.payment_id = razorpay_payment_id
            payment.signature = razorpay_signature
            db.commit()

        return {"status": "success", "payment_id": razorpay_payment_id}
    except razorpay.errors.SignatureVerificationError:
        # Update DB to failed if possible
        payment = (
            db.query(Payment).filter(Payment.order_id == razorpay_order_id).first()
        )
        if payment:
            payment.status = "failed"
            payment.payment_id = razorpay_payment_id
            payment.signature = razorpay_signature
            db.commit()

        raise HTTPException(status_code=400, detail="Invalid payment signature")
    except Exception as e:
        logger.error(f"Error verifying payment: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


def create_receipt_pdf(payment: Payment):
    os.makedirs("receipts", exist_ok=True)
    file_path = f"receipts/{payment.payment_id}.pdf"

    try:
        from weasyprint import HTML
    except ImportError as e:
        logger.error(
            f"WeasyPrint is not currently installed or configured properly (requires Pango/Cairo): {e}"
        )
        raise HTTPException(
            status_code=500,
            detail="PDF generation currently unavailable due to missing system dependencies.",
        )

    try:
        date_str = (
            payment.created_at.strftime("%d %b %Y")
            if payment.created_at is not None
            else datetime.now().strftime("%d %b %Y")
        )
    except Exception:
        date_str = datetime.now().strftime("%d %b %Y")

    receipt_id = (
        f"MMS-{datetime.now().year}-{payment.id:04d}"
        if getattr(payment, "id", None)
        else f"MMS-{datetime.now().year}-0000"
    )

    # Generate QR Code
    qr_data = f"https://makemystay.com/receipt/{payment.payment_id}"
    qr = qrcode.make(qr_data)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    qr_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

    # Load Logo
    logo_base64 = None
    logo_path = os.path.join(os.path.dirname(__file__), "../templates/logo.svg")
    try:
        if os.path.exists(logo_path):
            with open(logo_path, "rb") as image_file:
                logo_base64 = base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.warning(f"Failed to load or encode logo.svg: {e}")

    # Load Jinja2 Template
    try:
        template_loader = jinja2.FileSystemLoader(searchpath="./app/templates")
        template_env = jinja2.Environment(loader=template_loader)
        template = template_env.get_template("receipt.html")
    except Exception as e:
        logger.error(f"Error loading receipt template: {e}")
        raise e

    # Load Logo
    try:
        with open("./app/templates/logo.svg", "rb") as f:
            logo_base64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error loading logo: {e}")
        logo_base64 = ""

    # Render HTML template with context
    try:
        html_out = template.render(
            receipt_id=receipt_id,
            payment_id=payment.payment_id,
            date=date_str,
            status=str(payment.status).capitalize(),
            customer_name=payment.payer_name or "N/A",
            customer_phone=payment.payer_phone or "N/A",
            customer_email=payment.payer_email or "",
            amount=float(payment.amount or 0),
            qr_code_base64=qr_base64,
            logo_base64=logo_base64,
        )
    except Exception as e:
        logger.error(f"Error rendering receipt template: {e}")
        raise e

    # Convert HTML to PDF using WeasyPrint
    try:
        HTML(string=html_out).write_pdf(file_path)
    except Exception as e:
        logger.error(f"Error generating PDF from HTML: {e}")
        raise e

    return file_path


@router.get("/payments/receipt/{payment_id}")
def download_receipt(payment_id: str, db: Session = Depends(get_db)):
    payment = db.query(Payment).filter(Payment.payment_id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status != "success":
        raise HTTPException(status_code=400, detail="Payment is not successful")

    path = f"receipts/{payment_id}.pdf"
    if not os.path.exists(path):
        create_receipt_pdf(payment)

    return FileResponse(
        path, media_type="application/pdf", filename=f"receipt-{payment_id}.pdf"
    )


@router.get("/payments", response_model=List[PaymentSchema])
def get_payments(db: Session = Depends(get_db)):
    """List all payments."""
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    return payments
