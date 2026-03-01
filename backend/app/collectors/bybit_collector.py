# file: backend/app/collectors/bybit_collector.py
"""
Bybit V5 REST collector for market data.
Endpoints verified from: https://bybit-exchange.github.io/docs/v5/intro
"""
import aiohttp
import time
import structlog
from typing import Optional, Dict, Any
from app.models import NormalizedTick, FundingSnapshot
from app.config import settings

log = structlog.get_logger()

BASE_URL = settings.bybit_base_url


async def health_check() -> Dict[str, Any]:
    """Check Bybit API connectivity via server time endpoint."""
    url = f"{BASE_URL}/v5/market/time"
    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                latency_ms = (time.time() - t0) * 1000
                ok = data.get("retCode") == 0
                return {
                    "exchange": "bybit",
                    "status": "ok" if ok else "error",
                    "latency_ms": round(latency_ms, 1),
                    "server_time": data.get("result", {}).get("timeSecond"),
                    "raw": data,
                }
    except Exception as e:
        return {"exchange": "bybit", "status": "error", "error": str(e)}


async def fetch_ticker(symbol: str, category: str = "linear") -> Optional[NormalizedTick]:
    """
    Fetch latest ticker from Bybit V5.
    GET /v5/market/tickers?category={category}&symbol={symbol}
    """
    url = f"{BASE_URL}/v5/market/tickers"
    params = {"category": category, "symbol": symbol}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                if data.get("retCode") != 0:
                    log.error("bybit_ticker_error", symbol=symbol, response=data)
                    return None

                items = data.get("result", {}).get("list", [])
                if not items:
                    return None

                t = items[0]
                bid = float(t.get("bid1Price", 0))
                ask = float(t.get("ask1Price", 0))
                if bid == 0 or ask == 0:
                    return None

                return NormalizedTick(
                    ts=float(data.get("time", time.time() * 1000)),
                    exchange="bybit",
                    symbol=symbol,
                    market_type="perp" if category == "linear" else "spot",
                    bid=bid,
                    ask=ask,
                    bid_size=float(t.get("bid1Size", 0)) or None,
                    ask_size=float(t.get("ask1Size", 0)) or None,
                    mid=(bid + ask) / 2,
                    last_price=float(t.get("lastPrice", 0)) or None,
                    mark_price=float(t.get("markPrice", 0)) or None,
                    index_price=float(t.get("indexPrice", 0)) or None,
                    volume_24h=float(t.get("volume24h", 0)) or None,
                    open_interest=float(t.get("openInterest", 0)) or None,
                )
    except Exception as e:
        log.error("bybit_ticker_exception", symbol=symbol, error=str(e))
        return None


async def fetch_funding_rate(symbol: str) -> Optional[FundingSnapshot]:
    """
    Fetch current funding rate from Bybit V5.
    GET /v5/market/tickers?category=linear&symbol={symbol}
    Funding data is included in the linear ticker response.
    """
    url = f"{BASE_URL}/v5/market/tickers"
    params = {"category": "linear", "symbol": symbol}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
                if data.get("retCode") != 0:
                    return None

                items = data.get("result", {}).get("list", [])
                if not items:
                    return None

                t = items[0]
                rate_str = t.get("fundingRate", "")
                if not rate_str:
                    return None

                rate = float(rate_str)
                next_time_str = t.get("nextFundingTime", "")
                next_time = float(next_time_str) if next_time_str else None

                return FundingSnapshot(
                    ts=float(data.get("time", time.time() * 1000)),
                    exchange="bybit",
                    symbol=symbol,
                    funding_rate=rate,
                    predicted_rate=None,  # Bybit V5 ticker doesn't provide predicted
                    next_funding_time=next_time,
                    funding_interval_hours=8.0,  # Bybit standard
                    annualized_rate=rate * 1095,  # 365 * 24 / 8 = 1095
                )
    except Exception as e:
        log.error("bybit_funding_exception", symbol=symbol, error=str(e))
        return None
