from typing import Literal

from pydantic import BaseModel


class HealthCheckResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    database: str
    redis: str
    celery: str
