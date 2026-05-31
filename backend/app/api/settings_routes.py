from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from app.config.settings import settings, reload_settings
from app.utils.env_writer import update_env_file
from app.portfolio.service import reset_adapters

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

class APISettingsUpdate(BaseModel):
    # Manual
    bybit_api_key: Optional[str] = None
    bybit_api_secret: Optional[str] = None
    lighter_api_public_key: Optional[str] = None
    lighter_api_private_key: Optional[str] = None
    lighter_private_key: Optional[str] = None
    
    # AI
    ai_bybit_api_key: Optional[str] = None
    ai_bybit_api_secret: Optional[str] = None
    ai_lighter_api_public_key: Optional[str] = None
    ai_lighter_api_private_key: Optional[str] = None
    ai_lighter_private_key: Optional[str] = None

@router.get("/keys")
async def get_api_keys():
    """Get the current API keys (masked for security)."""
    def mask_key(k: str) -> str:
        if not k:
            return ""
        if len(k) < 8:
            return "***"
        return f"{k[:4]}...{k[-4:]}"

    return {
        "bybit_api_key": mask_key(settings.bybit_api_key),
        "bybit_api_secret": mask_key(settings.bybit_api_secret),
        "lighter_api_public_key": mask_key(settings.lighter_api_public_key),
        "lighter_api_private_key": mask_key(settings.lighter_api_private_key),
        "lighter_private_key": mask_key(settings.lighter_private_key),
        "ai_bybit_api_key": mask_key(settings.ai_bybit_api_key),
        "ai_bybit_api_secret": mask_key(settings.ai_bybit_api_secret),
        "ai_lighter_api_public_key": mask_key(settings.ai_lighter_api_public_key),
        "ai_lighter_api_private_key": mask_key(settings.ai_lighter_api_private_key),
        "ai_lighter_private_key": mask_key(settings.ai_lighter_private_key),
    }

@router.post("/keys")
async def update_api_keys(payload: APISettingsUpdate):
    """Update API keys in .env and reload settings."""
    updates = {}
    
    # Only update fields that are provided
    if payload.bybit_api_key is not None:
        updates["BYBIT_API_KEY"] = payload.bybit_api_key
    if payload.bybit_api_secret is not None:
        updates["BYBIT_API_SECRET"] = payload.bybit_api_secret
    if payload.lighter_private_key is not None:
        updates["LIGHTER_PRIVATE_KEY"] = payload.lighter_private_key
    if payload.lighter_api_public_key is not None:
        updates["LIGHTER_API_PUBLIC_KEY"] = payload.lighter_api_public_key
    if payload.lighter_api_private_key is not None:
        updates["LIGHTER_API_PRIVATE_KEY"] = payload.lighter_api_private_key
        
    if payload.ai_bybit_api_key is not None:
        updates["AI_BYBIT_API_KEY"] = payload.ai_bybit_api_key
    if payload.ai_bybit_api_secret is not None:
        updates["AI_BYBIT_API_SECRET"] = payload.ai_bybit_api_secret
    if payload.ai_lighter_private_key is not None:
        updates["AI_LIGHTER_PRIVATE_KEY"] = payload.ai_lighter_private_key
    if payload.ai_lighter_api_public_key is not None:
        updates["AI_LIGHTER_API_PUBLIC_KEY"] = payload.ai_lighter_api_public_key
    if payload.ai_lighter_api_private_key is not None:
        updates["AI_LIGHTER_API_PRIVATE_KEY"] = payload.ai_lighter_api_private_key

    if updates:
        import os
        # Update data/.env file to persist changes (which is mounted as a volume in Docker)
        update_env_file("data/.env", updates)
        # Update process environment variables so reload_settings() picks them up
        # since env vars have precedence over .env files in Pydantic Settings
        for k, v in updates.items():
            os.environ[k] = v
        reload_settings()
        reset_adapters()

    return {"message": "API keys updated successfully"}
