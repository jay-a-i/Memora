#backend/app/core/security.py

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from backend.app.core.config import settings

"""Look for the "APP_SECURITY_KEY" header in incoming requests"""
api_key_header = APIKeyHeader(name="APP_SECURITY_KEY")

async def verify_api_hitter(api_key: str = Security(api_key_header)):
    """
    Validates the incoming APP_SECURITY_KEY header.
    """

    master_key = getattr(settings, "APP_SECURITY_KEY", None)

    if not master_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Security key not set."
        ) 

    if api_key != master_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Forbidden: Invalid or missing API key"
        )

    return api_key      