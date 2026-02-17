from fastapi import APIRouter, HTTPException
from app.schemas.payment import ServiceFeeValidationRequest, ValidationResponse, PaymentInitiationRequest, PaymentResponse
from loguru import logger
import uuid


router = APIRouter()

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

@router.post("/payments/initiate", response_model=PaymentResponse)
def initiate_payment(data: PaymentInitiationRequest):
    logger.info(f"Initiating payment: {data.amount} {data.currency} via {data.method} for {data.payer_name}")
    
    # Mock payment processing logic
    transaction_id = f"TXN_{uuid.uuid4().hex[:12].upper()}"
    
    return {
        "transaction_id": transaction_id,
        "status": "success",
        "message": f"Payment of {data.currency} {data.amount} initiated successfully via {data.method}"
    }
