from fastapi import APIRouter, HTTPException
from app.schemas.payment import ServiceFeeValidationRequest, ValidationResponse
from loguru import logger

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
