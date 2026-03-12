"""
Auto-Hedge API routes.

POST /api/v1/auto-hedge/start   — start the monitor
POST /api/v1/auto-hedge/stop    — stop the monitor
GET  /api/v1/auto-hedge/status  — get current status
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.auto_hedge import get_auto_hedge_service

router = APIRouter(prefix="/api/v1/auto-hedge", tags=["auto-hedge"])


class StartRequest(BaseModel):
    symbol: str = "XAUTUSDT"
    poll_interval_s: float = 2.0
    min_delta: float = 0.001


@router.post("/start")
async def start_auto_hedge(req: StartRequest):
    svc = get_auto_hedge_service()
    try:
        await svc.start(
            symbol=req.symbol,
            poll_interval_s=req.poll_interval_s,
            min_delta=req.min_delta,
        )
        return {"status": "started", **svc.status()}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/stop")
async def stop_auto_hedge():
    svc = get_auto_hedge_service()
    try:
        await svc.stop()
        return {"status": "stopped"}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/status")
async def auto_hedge_status():
    svc = get_auto_hedge_service()
    return svc.status()
