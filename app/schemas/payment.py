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

class PaymentInitiationRequest(BaseModel):
    amount: float
    currency: str = "INR"
    method: str  # 'upi', 'card', 'netbanking'
    payer_name: Optional[str] = None
    payer_phone: Optional[str] = None
    payer_email: Optional[str] = None
    details: Optional[dict] = None

class PaymentResponse(BaseModel):
    transaction_id: str
    status: str
    message: str

