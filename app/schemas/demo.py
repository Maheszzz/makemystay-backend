from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, BaseModel, EmailStr


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

    model_config = ConfigDict(from_attributes=True)


class ScheduleDemoResponse(BaseModel):
    message: str
    meet_link: Optional[str] = None
    scheduled_at: datetime
