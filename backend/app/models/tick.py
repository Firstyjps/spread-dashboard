# file: backend/app/models/tick.py
from pydantic import BaseModel
from typing import Optional
import time


class NormalizedTick(BaseModel):
    """Exchange-agnostic tick data."""
    ts: float  # exchange timestamp (ms)
    exchange: str  # 'bybit' | 'lighter'
    symbol: str  # 'BTCUSDT'
    market_type: str  # 'perp' | 'spot'
    bid: float
    ask: float
    bid_size: Optional[float] = None
    ask_size: Optional[float] = None
    mid: float  # (bid + ask) / 2
    last_price: Optional[float] = None
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    volume_24h: Optional[float] = None
    open_interest: Optional[float] = None
    received_at: float = 0.0  # local receive time (ms)
    latency_ms: Optional[float] = None  # feed latency: received_at - exchange_ts

    def __init__(self, **data):
        if "mid" not in data and "bid" in data and "ask" in data:
            data["mid"] = (data["bid"] + data["ask"]) / 2
        if not data.get("received_at"):
            data["received_at"] = time.time() * 1000
        # Compute feed latency (only meaningful when ts is exchange-provided)
        if data.get("ts") and data.get("received_at") and data.get("latency_ms") is None:
            lat = data["received_at"] - data["ts"]
            # Only set if positive and reasonable (< 30s) — negative means clock skew
            if 0 < lat < 30000:
                data["latency_ms"] = round(lat, 1)
        super().__init__(**data)


class FundingSnapshot(BaseModel):
    """Funding rate data point."""
    ts: float
    exchange: str
    symbol: str
    funding_rate: float
    predicted_rate: Optional[float] = None
    next_funding_time: Optional[float] = None
    funding_interval_hours: Optional[float] = None
    annualized_rate: Optional[float] = None


class SpreadMetric(BaseModel):
    """Computed cross-exchange spread metrics."""
    ts: float
    symbol: str
    bybit_mid: float
    lighter_mid: float
    bybit_bid: float
    bybit_ask: float
    lighter_bid: float
    lighter_ask: float
    exchange_spread_mid: float  # (lighter_mid - bybit_mid) / bybit_mid
    long_spread: float  # (lighter_ask - bybit_ask) / bybit_ask
    short_spread: float  # (lighter_bid - bybit_bid) / bybit_bid
    bid_ask_spread_bybit: float  # (bybit_ask - bybit_bid) / bybit_mid
    bid_ask_spread_lighter: float  # (lighter_ask - lighter_bid) / lighter_mid
    basis_bybit: Optional[float] = None  # (mark_price - index_price) / index_price
    basis_bybit_bps: Optional[float] = None  # basis in basis points
    funding_diff: Optional[float] = None
    received_at: float = 0.0


class Alert(BaseModel):
    """Alert event."""
    ts: float
    alert_type: str  # 'spread_threshold' | 'stale_feed' | 'high_latency'
    symbol: Optional[str] = None
    severity: str  # 'info' | 'warning' | 'critical'
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None
