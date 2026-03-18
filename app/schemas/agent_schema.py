from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class AgentBase(BaseModel):
    name: str = Field(..., max_length=200)
    email: EmailStr = Field(..., max_length=200)
    phone: str = Field(..., max_length=20)
    is_active: bool = True
    max_capacity: int = Field(20, ge=0)
    location: Optional[str] = Field(None, max_length=200)


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    max_capacity: Optional[int] = None
    location: Optional[str] = None
    current_load: Optional[int] = None
    conversion_rate: Optional[float] = None


class AgentResponse(AgentBase):
    id: int
    current_load: int
    conversion_rate: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
