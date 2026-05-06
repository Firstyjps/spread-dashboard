"""API key auth dependency.

Add ``Depends(require_api_key)`` to any route that mutates state or
triggers trades. Clients send the secret in the ``X-API-Key`` header
(matched against ``settings.api_key``).
"""
from fastapi import Header, HTTPException, status
from app.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = settings.api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API auth not configured (API_KEY missing in env)",
        )
    if x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )
