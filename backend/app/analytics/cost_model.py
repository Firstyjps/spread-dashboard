# file: backend/app/analytics/cost_model.py
"""
Transaction cost model for cross-exchange arbitrage.
Pure functions — no external dependencies.

Default fees (used when actuals are unavailable):
  Bybit maker:  2.0 bps  (settings.maker_fee_rate = 0.0002)
  Lighter:      0.0 bps  (L2 DEX, zero trading fee)
  Slippage:     1.0 bps  (conservative estimate)
"""
from app.config import settings


def get_fee_bps() -> dict:
    """Return fee rates in bps from live settings (supports VIP tier changes via .env)."""
    return {
        "bybit_maker_bps": settings.maker_fee_rate * 10_000,
        "bybit_taker_bps": settings.taker_fee_rate * 10_000,
        "lighter_bps": 0.0,
        "slippage_bps": 1.0,
    }


def estimate_net_pnl_bps(
    spread_bps: float,
    bybit_fee_bps: float | None = None,
    lighter_fee_bps: float = 0.0,
    slippage_bps: float = 1.0,
) -> float:
    """
    Estimate net PnL in basis points after fees and slippage.

    Uses abs(spread_bps) because the direction of the trade flips
    to capture the spread regardless of sign.

    If bybit_fee_bps is None, reads from settings (supports VIP tier changes).

    Returns: net PnL in bps, rounded to 2dp.
    """
    if bybit_fee_bps is None:
        bybit_fee_bps = settings.maker_fee_rate * 10_000
    gross = abs(spread_bps)
    total_cost = bybit_fee_bps + lighter_fee_bps + slippage_bps
    return round(gross - total_cost, 2)


def cost_breakdown(spread_bps: float) -> dict:
    """Return detailed cost breakdown for a given spread (for UI tooltip)."""
    fees = get_fee_bps()
    gross = abs(spread_bps)
    total_cost = fees["bybit_maker_bps"] + fees["lighter_bps"] + fees["slippage_bps"]
    net = round(gross - total_cost, 2)
    return {
        "gross_bps": round(gross, 2),
        "bybit_fee_bps": round(fees["bybit_maker_bps"], 2),
        "lighter_fee_bps": round(fees["lighter_bps"], 2),
        "slippage_bps": round(fees["slippage_bps"], 2),
        "total_cost_bps": round(total_cost, 2),
        "net_bps": net,
    }


def is_profitable(
    spread_bps: float,
    bybit_fee_bps: float | None = None,
    lighter_fee_bps: float = 0.0,
    slippage_bps: float = 1.0,
) -> bool:
    """Check if an arb trade would be profitable after costs."""
    return estimate_net_pnl_bps(spread_bps, bybit_fee_bps, lighter_fee_bps, slippage_bps) > 0
