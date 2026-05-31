from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.config.settings import settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])

class AIConfigUpdate(BaseModel):
    is_dry_run: Optional[bool] = None
    trade_size_usd: Optional[float] = None
    max_open_trades: Optional[int] = None
    profit_threshold_bps: Optional[float] = None

@router.get("/status")
async def get_ai_status():
    """Get the current AI configuration and status."""
    # In a real app, you would read from the daemon's state.
    # For now, we return the settings.
    return {
        "status": "running",
        "is_dry_run": settings.risk_dry_run_enabled,
        "trade_size_usd": getattr(settings, "ai_trade_size_usd", 10.0),
        "max_open_trades": getattr(settings, "ai_max_open_trades", 1),
        "profit_threshold_bps": getattr(settings, "ai_profit_threshold_bps", 12.0),
        "active_trades": 0, # Placeholder
        "last_predicted_bps": 14.7 # Placeholder test value
    }

@router.post("/config")
async def update_ai_config(config: AIConfigUpdate):
    """Update AI configuration on the fly."""
    if config.is_dry_run is not None:
        settings.risk_dry_run_enabled = config.is_dry_run
    if config.trade_size_usd is not None:
        settings.ai_trade_size_usd = config.trade_size_usd
    if config.max_open_trades is not None:
        settings.ai_max_open_trades = config.max_open_trades
    if config.profit_threshold_bps is not None:
        settings.ai_profit_threshold_bps = config.profit_threshold_bps
        
    return {"message": "AI Configuration updated successfully"}
