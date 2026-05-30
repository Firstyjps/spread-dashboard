from fastapi import APIRouter, Query

from app.services.monitor import get_monitor_service

router = APIRouter(prefix="/api/v1/monitor", tags=["monitor"])


@router.get("/pairs")
async def monitor_pairs(group: str = Query(default="gold")):
    service = get_monitor_service()
    pairs = service.get_pairs(group)
    return {"group": group, "pairs": pairs, "count": len(pairs)}


@router.get("/spreads")
async def monitor_spreads(group: str = Query(default="gold")):
    service = get_monitor_service()
    return await service.fetch_current_spreads(group=group)


@router.get("/history")
async def monitor_history(
    pair: str,
    minutes: int = Query(default=60, ge=1, le=10080),
):
    service = get_monitor_service()
    history = await service.get_history(pair=pair, minutes=minutes)
    return {"pair": pair, "minutes": minutes, "history": history, "count": len(history)}
