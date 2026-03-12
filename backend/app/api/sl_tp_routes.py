"""
SL/TP API routes.

POST /api/v1/sl-tp/start   — start monitoring
POST /api/v1/sl-tp/stop    — stop monitoring
GET  /api/v1/sl-tp/status  — get current status
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.sl_tp import get_sl_tp_service

router = APIRouter(prefix="/api/v1/sl-tp", tags=["sl-tp"])


class StartRequest(BaseModel):
    symbol: str = "XAUTUSDT"
    sl_delta: float = 0.0  # price drop from entry to trigger SL (e.g. 300)
    tp_delta: float = 0.0  # price rise from entry to trigger TP (e.g. 300)
    poll_interval_s: float = 2.0


@router.post("/start")
async def start_sl_tp(req: StartRequest):
    svc = get_sl_tp_service()
    try:
        await svc.start(
            symbol=req.symbol,
            sl_delta=req.sl_delta,
            tp_delta=req.tp_delta,
            poll_interval_s=req.poll_interval_s,
        )
        return {"status": "started", **svc.status()}
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/stop")
async def stop_sl_tp():
    svc = get_sl_tp_service()
    try:
        await svc.stop()
        return {"status": "stopped"}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/reset")
async def reset_sl_tp():
    svc = get_sl_tp_service()
    svc.reset()
    return {"status": "reset", **svc.status()}


@router.get("/status")
async def sl_tp_status():
    svc = get_sl_tp_service()
    return svc.status()
