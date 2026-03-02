# file: backend/app/collectors/lighter_collector.py
"""
Lighter REST collector for market data.
Verified endpoints (mainnet: https://mainnet.zklighter.elliot.ai):
  - GET /                                -> status
  - GET /api/v1/orderBooks               -> all markets list (symbol, market_id, market_type)
  - GET /api/v1/orderBookDetails?market_id=X -> market details (last_trade_price, volume, etc.)
  - GET /api/v1/orderBookOrders?market_id=X&limit=N -> orderbook (asks[], bids[] with price, remaining_base_amount)
  - GET /api/v1/funding-rates            -> cross-exchange funding rates (market_id, exchange, symbol, rate)

Verified market_id mapping:
  ETH = 0, BTC = 1, SOL = 2, DOGE = 3 (fetch dynamically at startup via /api/v1/orderBooks)

Lighter uses short symbols: "BTC", "ETH", "SOL" (not "BTCUSDT").
We normalize: BTCUSDT -> market_id=1, ETHUSDT -> market_id=0, etc.
"""
import aiohttp
import time
import structlog
from typing import Optional, Dict, Any

from app.models import NormalizedTick, FundingSnapshot
from app.config import settings

log = structlog.get_logger()

BASE_URL = settings.lighter_base_url

# Symbol mapping: our normalized symbol -> Lighter market_id
# Populated dynamically at startup via fetch_market_ids()
SYMBOL_TO_MARKET_ID: Dict[str, int] = {}
MARKET_ID_TO_SYMBOL: Dict[int, str] = {}

# Market metadata: normalized symbol -> {size_decimals, price_decimals, min_base_amount}
MARKET_META: Dict[str, Dict[str, Any]] = {}

# Lighter short symbol -> our normalized symbol
# e.g., "BTC" -> "BTCUSDT", "ETH" -> "ETHUSDT"
LIGHTER_SYM_TO_NORMALIZED: Dict[str, str] = {}


def _normalize_symbol(lighter_sym: str) -> str:
    """Convert Lighter symbol (e.g., 'BTC') to our format ('BTCUSDT')."""
    s = lighter_sym.upper().strip()
    if s.endswith("USDT") or s.endswith("USDC"):
        return s
    return f"{s}USDT"


async def health_check() -> Dict[str, Any]:
    """Check Lighter API connectivity via status endpoint."""
    url = f"{BASE_URL}/"
    t0 = time.time()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                latency_ms = (time.time() - t0) * 1000
                if resp.status == 200:
                    text = await resp.text()
                    return {
                        "exchange": "lighter",
                        "status": "ok",
                        "latency_ms": round(latency_ms, 1),
                        "response": text[:200],
                    }
                return {
                    "exchange": "lighter",
                    "status": "error",
                    "http_status": resp.status,
                }
    except Exception as e:
        return {"exchange": "lighter", "status": "error", "error": str(e)}


async def fetch_market_ids() -> Dict[str, int]:
    """
    Fetch all markets from Lighter and build symbol mapping.
    Endpoint: GET /api/v1/orderBooks
    Response: { "code": 200, "order_books": [{ "symbol": "BTC", "market_id": 1, "market_type": "perp", ... }] }
    """
    global SYMBOL_TO_MARKET_ID, MARKET_ID_TO_SYMBOL, LIGHTER_SYM_TO_NORMALIZED, MARKET_META

    url = f"{BASE_URL}/api/v1/orderBooks"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    log.warning("lighter_market_fetch_failed", status=resp.status)
                    _use_fallback()
                    return SYMBOL_TO_MARKET_ID

                data = await resp.json()
                order_books = data.get("order_books", [])

                if not order_books:
                    log.warning("lighter_empty_order_books")
                    _use_fallback()
                    return SYMBOL_TO_MARKET_ID

                for m in order_books:
                    lighter_sym = m.get("symbol", "")
                    market_id = m.get("market_id")
                    market_type = m.get("market_type", "")
                    status = m.get("status", "")

                    if market_id is None or not lighter_sym:
                        continue
                    # Only map active perp markets for now
                    if status != "active" or market_type != "perp":
                        continue

                    normalized = _normalize_symbol(lighter_sym)
                    mid = int(market_id)

                    SYMBOL_TO_MARKET_ID[normalized] = mid
                    MARKET_ID_TO_SYMBOL[mid] = normalized
                    LIGHTER_SYM_TO_NORMALIZED[lighter_sym.upper()] = normalized

                    # Store scaling metadata for order placement
                    MARKET_META[normalized] = {
                        "size_decimals": int(m.get("supported_size_decimals", 4)),
                        "price_decimals": int(m.get("supported_price_decimals", 2)),
                        "min_base_amount": float(m.get("min_base_amount", 0)),
                    }

                log.info(
                    "lighter_markets_loaded",
                    count=len(SYMBOL_TO_MARKET_ID),
                    examples={k: v for i, (k, v) in enumerate(SYMBOL_TO_MARKET_ID.items()) if i < 5},
                )
                return SYMBOL_TO_MARKET_ID

    except Exception as e:
        log.error("lighter_market_fetch_exception", error=str(e))
        _use_fallback()
        return SYMBOL_TO_MARKET_ID


def _use_fallback():
    """Fallback mapping based on verified data (2026-03-01).
    Includes all 9 dashboard symbols + their scaling metadata."""
    global SYMBOL_TO_MARKET_ID, MARKET_ID_TO_SYMBOL, LIGHTER_SYM_TO_NORMALIZED, MARKET_META
    log.warning("lighter_using_fallback_market_ids")

    _FALLBACK = {
        # symbol:       (market_id, size_dec, price_dec, min_base, lighter_sym)
        "ETHUSDT":      (0,   4, 2, 0.005,   "ETH"),
        "BTCUSDT":      (1,   5, 1, 0.0002,  "BTC"),
        "SOLUSDT":      (2,   3, 3, 0.05,    "SOL"),
        "DOGEUSDT":     (3,   0, 6, 10,      "DOGE"),
        "XRPUSDT":      (7,   0, 6, 20,      "XRP"),
        "LINKUSDT":     (8,   1, 5, 1.0,     "LINK"),
        "AVAXUSDT":     (9,   2, 4, 0.5,     "AVAX"),
        "SUIUSDT":      (16,  1, 5, 3.0,     "SUI"),
        "XAUTUSDT":      (92,  4, 2, 0.003,   "XAUUSDT"),
        "XAUUSDT":      (92,  4, 2, 0.003,   "XAU"),
    }

    SYMBOL_TO_MARKET_ID = {}
    MARKET_ID_TO_SYMBOL = {}
    LIGHTER_SYM_TO_NORMALIZED = {}
    MARKET_META = {}

    for sym, (mid, s_dec, p_dec, min_b, l_sym) in _FALLBACK.items():
        SYMBOL_TO_MARKET_ID[sym] = mid
        MARKET_ID_TO_SYMBOL[mid] = sym
        LIGHTER_SYM_TO_NORMALIZED[l_sym] = sym
        MARKET_META[sym] = {
            "size_decimals": s_dec,
            "price_decimals": p_dec,
            "min_base_amount": min_b,
        }


def _resolve_symbol(symbol: str) -> str:
    """Resolve dashboard symbol to Lighter symbol via alias map.
    e.g., XAUTUSDT -> XAUUSDT (because Lighter uses XAU, not XAUT)."""
    return settings.lighter_aliases.get(symbol, symbol)


async def fetch_ticker(symbol: str) -> Optional[NormalizedTick]:
    """
    Fetch best bid/ask from Lighter orderbook.
    Endpoint: GET /api/v1/orderBookOrders?market_id={id}&limit=5
    Response: {
      "code": 200,
      "asks": [{"price": "67372.6", "remaining_base_amount": "0.01669", ...}],
      "bids": [{"price": "67369.7", "remaining_base_amount": "0.00027", ...}]
    }
    Asks are sorted lowest first, bids are sorted highest first.
    """
    lighter_symbol = _resolve_symbol(symbol)
    market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)
    if market_id is None:
        log.warning("lighter_unknown_symbol", symbol=symbol, lighter_symbol=lighter_symbol,
                     available=list(SYMBOL_TO_MARKET_ID.keys())[:10])
        return None

    url = f"{BASE_URL}/api/v1/orderBookOrders"
    params = {"market_id": market_id, "limit": 5}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    log.error("lighter_ticker_http_error", symbol=symbol, status=resp.status)
                    return None

                data = await resp.json()
                asks = data.get("asks", [])
                bids = data.get("bids", [])

                if not asks or not bids:
                    log.warning("lighter_empty_book", symbol=symbol, market_id=market_id)
                    return None

                # Best ask = first ask (lowest price), Best bid = first bid (highest price)
                best_ask = float(asks[0]["price"])
                best_bid = float(bids[0]["price"])
                ask_size = float(asks[0].get("remaining_base_amount", 0))
                bid_size = float(bids[0].get("remaining_base_amount", 0))

                if best_bid <= 0 or best_ask <= 0:
                    return None

                return NormalizedTick(
                    ts=time.time() * 1000,
                    exchange="lighter",
                    symbol=symbol,
                    market_type="perp",
                    bid=best_bid,
                    ask=best_ask,
                    bid_size=bid_size or None,
                    ask_size=ask_size or None,
                    mid=(best_bid + best_ask) / 2,
                )

    except Exception as e:
        log.error("lighter_ticker_exception", symbol=symbol, error=str(e))
        return None


# --- Funding rate cache (fetch once, use for all symbols) ---
_funding_cache: Dict[int, Dict] = {}  # market_id -> rate record
_funding_cache_ts: float = 0.0
_FUNDING_CACHE_TTL_S = 60.0  # refresh every 60s (avoids rate limits)


async def _refresh_funding_cache():
    """Fetch all funding rates once and cache them. Called at most once per TTL."""
    global _funding_cache, _funding_cache_ts

    now = time.time()
    if now - _funding_cache_ts < _FUNDING_CACHE_TTL_S and _funding_cache:
        return  # Cache still fresh

    url = f"{BASE_URL}/api/v1/funding-rates"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    log.error("lighter_funding_http_error", status=resp.status)
                    return

                data = await resp.json()
                rates = data.get("funding_rates", [])
                if not rates:
                    return

                # Index lighter rates by market_id
                new_cache: Dict[int, Dict] = {}
                for r in rates:
                    if r.get("exchange") == "lighter":
                        mid = r.get("market_id")
                        if mid is not None:
                            new_cache[mid] = r

                _funding_cache = new_cache
                _funding_cache_ts = now
                log.info("lighter_funding_cache_refreshed", count=len(new_cache))

    except Exception as e:
        log.error("lighter_funding_cache_exception", error=str(e))


async def fetch_funding_rate(symbol: str) -> Optional[FundingSnapshot]:
    """
    Get funding rate for a symbol from the cached funding data.
    The cache is refreshed at most once per 60 seconds to avoid rate limits.
    """
    lighter_symbol = _resolve_symbol(symbol)
    market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)
    if market_id is None:
        return None

    # Ensure cache is fresh
    await _refresh_funding_cache()

    lighter_rate = _funding_cache.get(market_id)
    if lighter_rate is None:
        return None

    try:
        rate = float(lighter_rate["rate"])
        interval_hours = 1.0

        return FundingSnapshot(
            ts=time.time() * 1000,
            exchange="lighter",
            symbol=symbol,
            funding_rate=rate,
            predicted_rate=None,
            next_funding_time=None,
            funding_interval_hours=interval_hours,
            annualized_rate=rate * (365 * 24 / interval_hours),
        )
    except Exception as e:
        log.error("lighter_funding_parse_error", symbol=symbol, error=str(e))
        return None
