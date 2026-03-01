# file: backend/app/api/routes.py
"""
REST API routes for the Spread Dashboard.
"""
import csv
import io
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from typing import Optional
from app.analytics.spread_engine import get_all_current_data, get_latest_tick, compute_spread, compute_zscore
from app.collectors import bybit_collector, lighter_collector
from app.storage.database import get_recent_spreads, get_spreads_by_time, get_recent_alerts
from app.config import settings

router = APIRouter(prefix="/api/v1")


@router.get("/health")
async def health():
    """System and exchange connectivity health check."""
    bybit_health = await bybit_collector.health_check()
    lighter_health = await lighter_collector.health_check()
    return {
        "status": "ok",
        "exchanges": {
            "bybit": bybit_health,
            "lighter": lighter_health,
        },
        "symbols": settings.symbol_list,
    }


@router.get("/prices")
async def prices():
    """Current prices from both exchanges."""
    return get_all_current_data()


@router.get("/spreads")
async def spreads(
    symbol: str = "BTCUSDT",
    limit: int = Query(default=500, le=5000),
    minutes: Optional[int] = Query(default=None, le=1440),
):
    """
    Current and historical spread data.
    Use `minutes` param to get time-based data (e.g., minutes=5 for last 5 min).
    Falls back to `limit` if `minutes` is not specified.
    """
    current = compute_spread(symbol)
    zscore = compute_zscore(symbol)
    if minutes is not None:
        history = await get_spreads_by_time(symbol, minutes)
    else:
        history = await get_recent_spreads(symbol, limit)
    return {
        "symbol": symbol,
        "current": current.model_dump() if current else None,
        "zscore": zscore,
        "history": history,
        "count": len(history),
    }


@router.get("/spreads/export")
async def export_spreads_csv(
    symbol: str = "BTCUSDT",
    minutes: int = Query(default=60, le=1440),
):
    """Export spread history as CSV file."""
    rows = await get_spreads_by_time(symbol, minutes)

    output = io.StringIO()
    if rows:
        fieldnames = [
            "ts", "symbol", "bybit_mid", "lighter_mid",
            "exchange_spread_mid", "long_spread", "short_spread",
            "bid_ask_spread_bybit", "bid_ask_spread_lighter",
            "basis_bybit_bps",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    output.seek(0)
    filename = f"spread_{symbol}_{minutes}m.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/funding")
async def funding():
    """Funding rates from both exchanges."""
    result = {}
    for symbol in settings.symbol_list:
        bybit_f = await bybit_collector.fetch_funding_rate(symbol)
        lighter_f = await lighter_collector.fetch_funding_rate(symbol)
        diff = None
        if bybit_f and lighter_f:
            diff = lighter_f.funding_rate - bybit_f.funding_rate
        result[symbol] = {
            "bybit": bybit_f.model_dump() if bybit_f else None,
            "lighter": lighter_f.model_dump() if lighter_f else None,
            "funding_diff": diff,
        }
    return result


@router.get("/alerts")
async def alerts(limit: int = Query(default=50, le=500)):
    """Recent alerts."""
    return await get_recent_alerts(limit)


@router.get("/config")
async def config():
    """Current configuration (non-sensitive)."""
    return {
        "symbols": settings.symbol_list,
        "poll_interval_ms": settings.poll_interval_ms,
        "spread_alert_bps": settings.spread_alert_bps,
        "stale_feed_timeout_s": settings.stale_feed_timeout_s,
        "latency_warning_ms": settings.latency_warning_ms,
    }
