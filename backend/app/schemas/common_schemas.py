# backend/app/schemas/common_schemas.py

from typing import Optional
from pydantic import BaseModel


class HealthCheckResponse(BaseModel):
    status: str = "healthy"
    database: str = "connected"
    version: str = "1.0.0"


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None