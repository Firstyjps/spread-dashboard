# file: backend/app/analytics/spread_engine.py
"""
Spread computation engine.
Computes cross-exchange metrics from normalized tick data.
"""
import time
import structlog
from collections import deque
from typing import Optional, Dict
from app.models import NormalizedTick, SpreadMetric

log = structlog.get_logger()

# In-memory latest ticks per exchange/symbol
latest_ticks: Dict[str, NormalizedTick] = {}  # key: "{exchange}:{symbol}"

# Rolling window for z-score computation
spread_history: Dict[str, deque] = {}  # key: symbol
ZSCORE_WINDOW = 100


def update_tick(tick: NormalizedTick):
    """Store latest tick in memory."""
    key = f"{tick.exchange}:{tick.symbol}"
    latest_ticks[key] = tick


def get_latest_tick(exchange: str, symbol: str) -> Optional[NormalizedTick]:
    """Get latest tick for exchange/symbol pair."""
    return latest_ticks.get(f"{exchange}:{symbol}")


def compute_spread(symbol: str) -> Optional[SpreadMetric]:
    """
    Compute cross-exchange spread metrics for a symbol.
    Requires both Bybit and Lighter ticks to be present.
    """
    bybit = get_latest_tick("bybit", symbol)
    lighter = get_latest_tick("lighter", symbol)

    if not bybit or not lighter:
        return None

    # Guard against zero prices
    if bybit.mid == 0 or lighter.mid == 0:
        return None
    if bybit.ask == 0 or bybit.bid == 0:
        return None

    now = time.time() * 1000

    # Core spread formulas
    exchange_spread_mid = (lighter.mid - bybit.mid) / bybit.mid
    long_spread = (lighter.ask - bybit.ask) / bybit.ask
    short_spread = (lighter.bid - bybit.bid) / bybit.bid

    # Per-exchange bid-ask spread
    ba_bybit = (bybit.ask - bybit.bid) / bybit.mid
    ba_lighter = (lighter.ask - lighter.bid) / lighter.mid

    metric = SpreadMetric(
        ts=now,
        symbol=symbol,
        bybit_mid=bybit.mid,
        lighter_mid=lighter.mid,
        bybit_bid=bybit.bid,
        bybit_ask=bybit.ask,
        lighter_bid=lighter.bid,
        lighter_ask=lighter.ask,
        exchange_spread_mid=exchange_spread_mid,
        long_spread=long_spread,
        short_spread=short_spread,
        bid_ask_spread_bybit=ba_bybit,
        bid_ask_spread_lighter=ba_lighter,
        received_at=now,
    )

    # Update rolling history for z-score
    if symbol not in spread_history:
        spread_history[symbol] = deque(maxlen=ZSCORE_WINDOW)
    spread_history[symbol].append(exchange_spread_mid)

    return metric


def compute_zscore(symbol: str) -> Optional[float]:
    """Compute rolling z-score of exchange spread."""
    history = spread_history.get(symbol)
    if not history or len(history) < 10:
        return None

    values = list(history)
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    if variance == 0:
        return 0.0
    std = variance ** 0.5
    current = values[-1]
    return (current - mean) / std


def compute_imbalance(tick: NormalizedTick) -> Optional[float]:
    """Compute top-of-book orderbook imbalance."""
    if tick.bid_size is None or tick.ask_size is None:
        return None
    total = tick.bid_size + tick.ask_size
    if total == 0:
        return None
    return (tick.bid_size - tick.ask_size) / total


def get_all_current_data() -> Dict:
    """Get snapshot of all current data for API/WS broadcast."""
    result = {}
    symbols_seen = set()

    for key, tick in latest_ticks.items():
        symbols_seen.add(tick.symbol)

    for symbol in symbols_seen:
        bybit = get_latest_tick("bybit", symbol)
        lighter = get_latest_tick("lighter", symbol)
        spread = compute_spread(symbol)
        zscore = compute_zscore(symbol)

        result[symbol] = {
            "bybit": bybit.model_dump() if bybit else None,
            "lighter": lighter.model_dump() if lighter else None,
            "spread": spread.model_dump() if spread else None,
            "zscore": zscore,
            "imbalance_bybit": compute_imbalance(bybit) if bybit else None,
            "imbalance_lighter": compute_imbalance(lighter) if lighter else None,
        }

    return result
