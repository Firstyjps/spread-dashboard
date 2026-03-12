"""
REST API routes for the Spread Dashboard.
"""
import asyncio
import csv
import io
import structlog
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from typing import Optional

from decimal import Decimal
from pydantic import BaseModel
from app.analytics.spread_engine import get_all_current_data, get_latest_tick, compute_spread, compute_zscore
from app.analytics.cost_model import estimate_net_pnl_bps, cost_breakdown
from app.collectors import bybit_collector, lighter_collector
from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.storage.database import get_recent_spreads, get_spreads_by_time, get_all_spreads, get_recent_alerts
from app.config import settings
from app.utils.percentiles import compute_percentiles
from app.execution import TradeRequest
from app.services.executor import ArbitrageExecutor
from app.execution.maker_engine import smart_execute_maker, MakerConfig
from app.execution.iceberg_executor import (
    execute_iceberg, IcebergConfig, PricePolicy, Urgency,
)
from app.execution.rate_limiter import TokenBucketRateLimiter, RateLimiterConfig

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
    symbol: str = "XAUTUSDT",
    limit: int = Query(default=500, le=5000),
    minutes: Optional[int] = Query(default=None, le=10080),
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

    # Compute P10/P90 percentile stats on mid spread (same data the chart shows)
    mid_values = [row.get("exchange_spread_mid") for row in history]
    stats = compute_percentiles(mid_values)
    log.debug(
        "spread_percentiles",
        symbol=symbol,
        n=stats.n,
        p10=stats.p10,
        p90=stats.p90,
    )

    # Compute net PnL from current spread's dominant leg
    net_pnl_bps = None
    costs = None
    if current:
        long_bps = abs(current.long_spread) * 10_000
        short_bps = abs(current.short_spread) * 10_000
        dominant_bps = max(long_bps, short_bps)
        net_pnl_bps = estimate_net_pnl_bps(dominant_bps)
        costs = cost_breakdown(dominant_bps)

    return {
        "symbol": symbol,
        "current": current.model_dump() if current else None,
        "zscore": zscore,
        "net_pnl_bps": net_pnl_bps,
        "cost_breakdown": costs,
        "history": history,
        "count": len(history),
        "stats": stats.to_dict(),
    }


@router.get("/spreads/history")
async def spreads_history(symbol: str = "XAUTUSDT"):
    """All historical spread data (downsampled to 50k points max)."""
    history = await get_all_spreads(symbol)
    mid_values = [row.get("exchange_spread_mid") for row in history]
    stats = compute_percentiles(mid_values)
    return {
        "symbol": symbol,
        "history": history,
        "count": len(history),
        "stats": stats.to_dict(),
    }


@router.get("/spreads/export")
async def export_spreads_csv(
    symbol: str = "XAUTUSDT",
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


# --- Shared clients for read-only endpoints (reused across requests) ---
_shared_bybit_client: Optional[BybitClient] = None
_shared_lighter_client: Optional[LighterClient] = None


def _get_shared_bybit() -> BybitClient:
    global _shared_bybit_client
    if _shared_bybit_client is None:
        _shared_bybit_client = BybitClient(settings)
    return _shared_bybit_client


def _get_shared_lighter() -> LighterClient:
    global _shared_lighter_client
    if _shared_lighter_client is None:
        _shared_lighter_client = LighterClient(settings)
    return _shared_lighter_client


@router.get("/positions")
async def get_positions(symbol: str = "XAUTUSDT"):
    """Get current positions on both exchanges for a symbol, with funding & theoretical PnL."""
    try:
        bybit_pos, lighter_pos, funding_data = await asyncio.wait_for(
            asyncio.gather(
                _get_shared_bybit().get_position(symbol),
                _get_shared_lighter().get_position(symbol),
                _fetch_funding_for_position(symbol),
            ),
            timeout=15.0,
        )

        # Compute theoretical PnL from spread difference
        theoretical = _compute_theoretical_pnl(bybit_pos, lighter_pos, symbol)

        return {
            "symbol": symbol,
            "bybit": bybit_pos,
            "lighter": lighter_pos,
            "funding": funding_data,
            "theoretical": theoretical,
        }
    except asyncio.TimeoutError:
        log.error("get_positions_timeout", symbol=symbol)
        raise HTTPException(status_code=504, detail="Position query timed out")
    except Exception as e:
        log.error("get_positions_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


async def _fetch_funding_for_position(symbol: str) -> dict:
    """Fetch funding rates and estimate 8h cost for current position."""
    try:
        bybit_f = await bybit_collector.fetch_funding_rate(symbol)
        lighter_f = await lighter_collector.fetch_funding_rate(symbol)
        bybit_rate = bybit_f.funding_rate if bybit_f else None
        lighter_rate = lighter_f.funding_rate if lighter_f else None
        # Lighter is 1h cycle, normalize to 8h for comparison
        lighter_8h = lighter_rate * 8 if lighter_rate is not None else None
        # Net: short Bybit receives when positive, long Lighter pays when positive
        net_8h = (bybit_rate - lighter_8h) if (bybit_rate is not None and lighter_8h is not None) else None
        return {
            "bybit_rate": bybit_rate,
            "lighter_rate": lighter_rate,
            "lighter_8h": lighter_8h,
            "net_8h_rate": net_8h,
        }
    except Exception as e:
        log.warning("funding_fetch_for_position_failed", error=str(e))
        return {"bybit_rate": None, "lighter_rate": None, "lighter_8h": None, "net_8h_rate": None}


def _compute_theoretical_pnl(bybit_pos: dict, lighter_pos: dict, symbol: str) -> dict:
    """Compute theoretical PnL based on entry spread vs current spread.

    Theoretical $ = (entry_spread_bps - current_spread_bps) / 10000 * notional
    This gives a clean view independent of each exchange's mark price drift.
    """
    bybit_entry = bybit_pos.get("entry_price", 0)
    lighter_entry = lighter_pos.get("entry_price", 0)
    bybit_amt = bybit_pos.get("amount", 0)
    lighter_amt = lighter_pos.get("amount", 0)

    if not (bybit_entry > 0 and lighter_entry > 0 and bybit_amt > 0):
        return {"entry_bps": None, "current_bps": None, "diff_bps": None, "pnl_usd": None}

    # Entry spread
    entry_bps = (lighter_entry - bybit_entry) / bybit_entry * 10000

    # Current spread from live data
    spread = compute_spread(symbol)
    if not spread:
        return {"entry_bps": round(entry_bps, 2), "current_bps": None, "diff_bps": None, "pnl_usd": None}

    current_bps = spread.exchange_spread_mid * 10000

    # PnL = spread captured at entry minus current spread cost to close
    diff_bps = entry_bps - current_bps
    # Notional = avg of both sides
    notional = (bybit_entry * bybit_amt + lighter_entry * lighter_amt) / 2
    pnl_usd = diff_bps / 10000 * notional

    return {
        "entry_bps": round(entry_bps, 2),
        "current_bps": round(current_bps, 2),
        "diff_bps": round(diff_bps, 2),
        "pnl_usd": round(pnl_usd, 4),
    }


@router.post("/execute")
async def execute_trade(req: TradeRequest):
    mapped_side = SIDE_MAP.get(req.side, req.side)

    try:
        async with ArbitrageExecutor(settings) as executor:
            results = await executor.run_arb(req.symbol, mapped_side, req.amount)

            lighter_res, bybit_res = results[0], results[1]

            # Bybit aborted or below threshold (no positions opened)
            if lighter_res is None:
                bybit_detail = bybit_res.to_dict() if hasattr(bybit_res, "to_dict") else str(bybit_res)
                status = "aborted" if hasattr(bybit_res, "status") and bybit_res.status == "aborted" else "below_threshold"
                return {
                    "status": status,
                    "detail": f"Bybit {status}: {bybit_res.detail if hasattr(bybit_res, 'detail') else 'fill below threshold'}",
                    "bybit": bybit_detail,
                }

            return {
                "status": "success",
                "detail": f"Sequential Arb for {req.symbol} ({mapped_side}, qty={req.amount})",
                "bybit": bybit_res.to_dict() if hasattr(bybit_res, "to_dict") else str(bybit_res),
                "lighter": str(lighter_res),
                "matched_qty": str(bybit_res.filled_qty) if hasattr(bybit_res, "filled_qty") else str(req.amount),
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ClosePositionRequest(BaseModel):
    symbol: str


@router.post("/execute/close_all")
async def close_all_positions(req: ClosePositionRequest):
    try:
        async with ArbitrageExecutor(settings) as executor:
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


# ─── Iceberg Executor ────────────────────────────────────────────

class IcebergRequest(BaseModel):
    symbol: str = "XAUTUSDT"
    side: str = "Buy"
    total_qty: float = 0.01
    child_qty: float = 0.001
    max_active_children: int = 1
    price_policy: str = "PASSIVE"           # PASSIVE | MID | CHASE
    urgency: str = "normal"                  # passive | normal | aggressive
    price_limit: Optional[float] = None
    reduce_only: bool = False
    max_runtime_s: float = 120.0
    max_cancels: int = 30
    reprice_threshold_bps: int = 5
    max_slippage_bps: int = 50


# Module-level shared rate limiter (created once, reused across requests)
_shared_rate_limiter: Optional[TokenBucketRateLimiter] = None


def _get_rate_limiter() -> TokenBucketRateLimiter:
    global _shared_rate_limiter
    if _shared_rate_limiter is None:
        _shared_rate_limiter = TokenBucketRateLimiter(
            RateLimiterConfig(
                max_tokens=settings.rate_limit_max_tokens,
                refill_rate=settings.rate_limit_refill_rate,
            )
        )
    return _shared_rate_limiter


@router.post("/execute/iceberg")
async def execute_iceberg_order(req: IcebergRequest):
    """Synthetic Iceberg Executor on Bybit. For dev/testing."""
    if req.side not in ("Buy", "Sell"):
        raise HTTPException(status_code=400, detail="side must be 'Buy' or 'Sell'")
    if req.total_qty <= 0 or req.child_qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be positive")
    if req.child_qty > req.total_qty:
        raise HTTPException(status_code=400, detail="child_qty must be <= total_qty")

    try:
        price_policy = PricePolicy(req.price_policy)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid price_policy: {req.price_policy}")
    try:
        urgency = Urgency(req.urgency)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid urgency: {req.urgency}")

    client = BybitClient(settings)
    iceberg_cfg = IcebergConfig(
        child_qty=Decimal(str(req.child_qty)),
        max_active_children=req.max_active_children,
        price_policy=price_policy,
        urgency=urgency,
        price_limit=Decimal(str(req.price_limit)) if req.price_limit else None,
        reduce_only=req.reduce_only,
        poll_interval_ms=settings.iceberg_poll_interval_ms,
        cooldown_ms=settings.iceberg_cooldown_ms,
        max_runtime_s=req.max_runtime_s,
        reprice_threshold_bps=req.reprice_threshold_bps,
        max_cancels=req.max_cancels,
        max_slippage_bps=req.max_slippage_bps,
        max_retries=settings.iceberg_max_retries,
        taker_fee_rate=settings.taker_fee_rate,
        maker_fee_rate=settings.maker_fee_rate,
    )

    try:
        result = await execute_iceberg(
            client=client,
            symbol=req.symbol,
            side=req.side,
            total_qty=Decimal(str(req.total_qty)),
            config=iceberg_cfg,
            rate_limiter=_get_rate_limiter(),
        )
        return result.to_dict()
    except Exception as e:
        log.error("iceberg_test_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
