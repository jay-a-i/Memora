#backend/app/core/security.py

import secrets

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from src.core.config import settings

"""Look for the "APP_SECURITY_KEY" header in incoming requests"""
api_key_header = APIKeyHeader(name="APP_SECURITY_KEY", auto_error=False)


async def verify_api_hitter(api_key: str | None = Security(api_key_header)):
    """
    Validates the incoming APP_SECURITY_KEY header.
    """

    master_key = getattr(settings, "APP_API_KEY", None)

    if not master_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server configuration error: Security key not set.",
        )
    if not api_key or not secrets.compare_digest(
        api_key.encode("utf-8"), master_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Forbidden: Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key