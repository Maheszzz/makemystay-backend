from datetime import datetime
from typing import Optional

from pydantic import BaseModel


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


class PaymentSchema(BaseModel):
    id: int
    amount: float
    currency: str
    payment_type: str
    status: str
    order_id: str
    payment_id: Optional[str] = None
    payer_name: Optional[str] = None
    payer_email: Optional[str] = None
    payer_phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PaymentTransactionSchema(BaseModel):
    id: int
    order_id: str
    payment_id: Optional[str] = None
    bank_rrn: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    created_at: datetime
    amount: float
    currency: str
    status: str
    db_status: str
    method: Optional[str] = None
    payment_type: Optional[str] = None
    detail_url: Optional[str] = None
    source: Optional[str] = None
