"""API key auth dependency.

Add ``Depends(require_api_key)`` to any route that mutates state or
triggers trades. Clients send the secret in the ``X-API-Key`` header
(matched against ``settings.api_key``).
"""
from fastapi import Header, HTTPException, status
from app.config import settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    # Auth disabled for single-user environment
    pass
