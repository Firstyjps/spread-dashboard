"""
REST API routes for the Spread Dashboard.
"""
import csv
import io
import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from decimal import Decimal
from pydantic import BaseModel
from app.analytics.spread_engine import get_all_current_data, get_latest_tick, compute_spread, compute_zscore
from app.collectors import bybit_collector, lighter_collector
from app.collectors.bybit_client import BybitClient
from app.storage.database import get_recent_spreads, get_spreads_by_time, get_recent_alerts
from app.config import settings
from app.execution import TradeRequest
from app.services.executor import ArbitrageExecutor
from app.execution.maker_engine import smart_execute_maker, MakerConfig

log = structlog.get_logger()

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

# --- Side mapping: frontend → executor ---
SIDE_MAP = {
    "LONG_LIGHTER": "BUY_LIGHTER_SELL_BYBIT",
    "SHORT_LIGHTER": "SELL_LIGHTER_BUY_BYBIT",
}


@router.get("/positions")
async def get_positions(symbol: str = "BTCUSDT"):
    """Get current positions on both exchanges for a symbol."""
    try:
        executor = ArbitrageExecutor(settings)
        bybit_pos = await executor.bybit.get_position(symbol)
        lighter_pos = await executor.lighter.get_position(symbol)
        return {"symbol": symbol, "bybit": bybit_pos, "lighter": lighter_pos}
    except Exception as e:
        log.error("get_positions_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_trade(req: TradeRequest):
    executor = ArbitrageExecutor(settings)
    mapped_side = SIDE_MAP.get(req.side, req.side)

    try:
        results = await executor.run_arb(req.symbol, mapped_side, req.amount)

        for res in results:
            if isinstance(res, Exception):
                raise HTTPException(status_code=500, detail=f"Execution Failed: {str(res)}")

        return {
            "status": "success",
            "detail": f"Atomic Arb triggered for {req.symbol} ({mapped_side}, qty={req.amount})",
            "results": str(results),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ClosePositionRequest(BaseModel):
    symbol: str


@router.post("/execute/close_all")
async def close_all_positions(req: ClosePositionRequest):
    try:
        executor = ArbitrageExecutor(settings)
        result = await executor.emergency_close_auto(symbol=req.symbol)
        return result
    except Exception as e:
        log.error("close_all_error", symbol=req.symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


class MakerTestRequest(BaseModel):
    symbol: str = "XAUTUSDT"
    side: str = "Buy"
    qty: float = 0.001


@router.post("/execute/maker_test")
async def test_maker_engine(req: MakerTestRequest):
    """Test maker engine on Bybit only (no Lighter). For dev/testing."""
    if req.side not in ("Buy", "Sell"):
        raise HTTPException(status_code=400, detail="side must be 'Buy' or 'Sell'")

    client = BybitClient(settings)
    maker_cfg = MakerConfig(
        max_time_s=settings.maker_max_time_s,
        reprice_interval_ms=settings.maker_reprice_interval_ms,
        max_reprices=settings.maker_max_reprices,
        aggressiveness=settings.maker_aggressiveness,
        allow_market_fallback=settings.maker_allow_market_fallback,
        maker_fee_rate=settings.maker_fee_rate,
        taker_fee_rate=settings.taker_fee_rate,
        spread_guard_ticks=settings.maker_spread_guard_ticks,
        vol_window=settings.maker_vol_window,
        vol_limit_ticks=settings.maker_vol_limit_ticks,
        max_deviation_ticks=settings.maker_max_deviation_ticks,
    )

    try:
        result = await smart_execute_maker(
            client=client,
            symbol=req.symbol,
            side=req.side,
            target_qty=Decimal(str(req.qty)),
            config=maker_cfg,
        )
        return result.to_dict()
    except Exception as e:
        log.error("maker_test_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))