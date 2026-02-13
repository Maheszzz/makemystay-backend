from pydantic import BaseModel
from typing import Optional

class ServiceFeeValidationRequest(BaseModel):
    property_id: int
    property_type: str
    service_fee_amount: float
    service_fee_type: str  # 'sharing', 'private', 'fixed'

class ValidationResponse(BaseModel):
    valid: bool
    message: str
