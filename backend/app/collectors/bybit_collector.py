# file: backend/app/collectors/bybit_collector.py
"""
Bybit V5 REST collector for market data.
Uses persistent aiohttp session for connection pooling (no per-request SSL handshake).
"""
import aiohttp
import time
import structlog
from typing import Optional, Dict, Any
from app.models import NormalizedTick, FundingSnapshot
from app.config import settings

log = structlog.get_logger()

BASE_URL = settings.bybit_base_url

# ---------- Persistent session ----------
_session: Optional[aiohttp.ClientSession] = None
_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=_TIMEOUT,
            connector=aiohttp.TCPConnector(limit=20, ttl_dns_cache=300),
        )
    return _session


async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


# ---------- Funding rate cache (like Lighter) ----------
_funding_cache: Dict[str, Dict] = {}  # symbol -> ticker data
_funding_cache_ts: float = 0.0
_FUNDING_CACHE_TTL_S = 60.0


async def health_check() -> Dict[str, Any]:
    """Check Bybit API connectivity via server time endpoint."""
    url = f"{BASE_URL}/v5/market/time"
    t0 = time.time()
    try:
        session = await _get_session()
        async with session.get(url) as resp:
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
        session = await _get_session()
        async with session.get(url, params=params) as resp:
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

            # Cache funding data from ticker response (avoids separate API call)
            rate_str = t.get("fundingRate", "")
            if rate_str and category == "linear":
                _funding_cache[symbol] = t
                global _funding_cache_ts
                _funding_cache_ts = time.time()

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
    Get funding rate for a symbol.
    Uses cached data from fetch_ticker (same endpoint) to avoid duplicate calls.
    Falls back to direct API call if cache is stale (>60s).
    """
    # Try cache first (populated by fetch_ticker)
    t = _funding_cache.get(symbol)

    # If cache miss or stale, fetch directly
    if not t or (time.time() - _funding_cache_ts > _FUNDING_CACHE_TTL_S):
        url = f"{BASE_URL}/v5/market/tickers"
        params = {"category": "linear", "symbol": symbol}
        try:
            session = await _get_session()
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                if data.get("retCode") != 0:
                    return None
                items = data.get("result", {}).get("list", [])
                if not items:
                    return None
                t = items[0]
        except Exception as e:
            log.error("bybit_funding_exception", symbol=symbol, error=str(e))
            return None

    rate_str = t.get("fundingRate", "")
    if not rate_str:
        return None

    rate = float(rate_str)
    next_time_str = t.get("nextFundingTime", "")
    next_time = float(next_time_str) if next_time_str else None

    return FundingSnapshot(
        ts=time.time() * 1000,
        exchange="bybit",
        symbol=symbol,
        funding_rate=rate,
        predicted_rate=None,
        next_funding_time=next_time,
        funding_interval_hours=8.0,
        annualized_rate=rate * 1095,  # 365 * 24 / 8
    )
