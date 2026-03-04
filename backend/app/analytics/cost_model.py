# file: backend/app/analytics/cost_model.py
"""
Transaction cost model for cross-exchange arbitrage.
Pure functions — no external dependencies.

Default fees:
  Bybit maker:  2.0 bps  (settings.maker_fee_rate = 0.0002)
  Lighter:      0.0 bps  (L2 DEX, zero trading fee)
  Slippage:     1.0 bps  (conservative estimate)
"""


def estimate_net_pnl_bps(
    spread_bps: float,
    bybit_fee_bps: float = 2.0,
    lighter_fee_bps: float = 0.0,
    slippage_bps: float = 1.0,
) -> float:
    """
    Estimate net PnL in basis points after fees and slippage.

    Uses abs(spread_bps) because the direction of the trade flips
    to capture the spread regardless of sign.

    Returns: net PnL in bps, rounded to 2dp.
    """
    gross = abs(spread_bps)
    total_cost = bybit_fee_bps + lighter_fee_bps + slippage_bps
    return round(gross - total_cost, 2)


def is_profitable(
    spread_bps: float,
    bybit_fee_bps: float = 2.0,
    lighter_fee_bps: float = 0.0,
    slippage_bps: float = 1.0,
) -> bool:
    """Check if an arb trade would be profitable after costs."""
    return estimate_net_pnl_bps(spread_bps, bybit_fee_bps, lighter_fee_bps, slippage_bps) > 0
