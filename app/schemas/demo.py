from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class DemoBookingCreate(BaseModel):
    name: str
    email: EmailStr
    phone: str
    company: Optional[str] = None
    units: Optional[str] = None
    selected_slot: datetime

class DemoBookingResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    company: Optional[str] = None
    units: Optional[str] = None
    selected_slot: datetime
    status: str
    meeting_link: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True

class ScheduleDemoResponse(BaseModel):
    message: str
    meet_link: Optional[str] = None
    scheduled_at: datetime
