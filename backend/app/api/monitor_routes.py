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
    timeframe: str = Query(default="raw", regex="^(raw|1m|5m|15m|1h|4h)$"),
):
    """Get spread history for a pair, optionally downsampled to a timeframe."""
    service = get_monitor_service()
    history = await service.get_history(pair=pair, minutes=minutes)

    # Downsample if timeframe != raw
    if timeframe != "raw" and history:
        history = _downsample(history, timeframe)

    return {"pair": pair, "minutes": minutes, "timeframe": timeframe, "history": history, "count": len(history)}


def _downsample(rows: list[dict], timeframe: str) -> list[dict]:
    """Downsample history rows by taking the last row per time bucket."""
    bucket_ms = {
        "1m": 60_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000,
    }.get(timeframe, 0)
    if bucket_ms == 0:
        return rows

    buckets: dict[int, dict] = {}
    for row in rows:
        ts = row.get("ts", 0)
        bucket_key = int(ts // bucket_ms)
        buckets[bucket_key] = row  # last row wins per bucket

    return [buckets[k] for k in sorted(buckets.keys())]
