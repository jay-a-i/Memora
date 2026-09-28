# backend/app/schemas/common_schemas.py

from typing import Optional, Dict
from pydantic import BaseModel


class HealthCheckResponse(BaseModel):
    status: str = "healthy"
    database: Dict[str, str]
    version: str


class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None