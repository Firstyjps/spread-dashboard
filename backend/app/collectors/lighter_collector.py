# file: backend/app/collectors/lighter_collector.py
"""
Lighter REST collector for market data.
Uses persistent aiohttp session for connection pooling.
"""
import asyncio
import aiohttp
import time
import structlog
from typing import Optional, Dict, Any

from app.models import NormalizedTick, FundingSnapshot
from app.config import settings

log = structlog.get_logger()

BASE_URL = settings.lighter_base_url

# ---------- Persistent session + rate limit ----------
_session: Optional[aiohttp.ClientSession] = None
_TIMEOUT = aiohttp.ClientTimeout(total=5)
_semaphore: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    """Limit concurrent Lighter requests to avoid 429 rate limits."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(2)  # max 2 concurrent requests to avoid 429
    return _semaphore


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=_TIMEOUT,
            connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
        )
    return _session


async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


# ---------- Symbol mapping ----------
SYMBOL_TO_MARKET_ID: Dict[str, int] = {}
MARKET_ID_TO_SYMBOL: Dict[int, str] = {}
MARKET_META: Dict[str, Dict[str, Any]] = {}
LIGHTER_SYM_TO_NORMALIZED: Dict[str, str] = {}


def _normalize_symbol(lighter_sym: str) -> str:
    s = lighter_sym.upper().strip()
    if s.endswith("USDT") or s.endswith("USDC"):
        return s
    return f"{s}USDT"


# ---------- Health check ----------
async def health_check() -> Dict[str, Any]:
    url = f"{BASE_URL}/"
    t0 = time.time()
    try:
        session = await _get_session()
        async with session.get(url) as resp:
            latency_ms = (time.time() - t0) * 1000
            if resp.status == 200:
                text = await resp.text()
                return {
                    "exchange": "lighter",
                    "status": "ok",
                    "latency_ms": round(latency_ms, 1),
                    "response": text[:200],
                }
            return {"exchange": "lighter", "status": "error", "http_status": resp.status}
    except Exception as e:
        return {"exchange": "lighter", "status": "error", "error": str(e)}


# ---------- Market IDs ----------
async def fetch_market_ids() -> Dict[str, int]:
    global SYMBOL_TO_MARKET_ID, MARKET_ID_TO_SYMBOL, LIGHTER_SYM_TO_NORMALIZED, MARKET_META

    url = f"{BASE_URL}/api/v1/orderBooks"
    try:
        session = await _get_session()
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
                if status != "active" or market_type != "perp":
                    continue

                normalized = _normalize_symbol(lighter_sym)
                mid = int(market_id)

                SYMBOL_TO_MARKET_ID[normalized] = mid
                MARKET_ID_TO_SYMBOL[mid] = normalized
                LIGHTER_SYM_TO_NORMALIZED[lighter_sym.upper()] = normalized

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
    global SYMBOL_TO_MARKET_ID, MARKET_ID_TO_SYMBOL, LIGHTER_SYM_TO_NORMALIZED, MARKET_META
    log.warning("lighter_using_fallback_market_ids")

    _FALLBACK = {
        "ETHUSDT":   (0,   4, 2, 0.005,   "ETH"),
        "BTCUSDT":   (1,   5, 1, 0.0002,  "BTC"),
        "SOLUSDT":   (2,   3, 3, 0.05,    "SOL"),
        "DOGEUSDT":  (3,   0, 6, 10,      "DOGE"),
        "XRPUSDT":   (7,   0, 6, 20,      "XRP"),
        "LINKUSDT":  (8,   1, 5, 1.0,     "LINK"),
        "AVAXUSDT":  (9,   2, 4, 0.5,     "AVAX"),
        "SUIUSDT":   (16,  1, 5, 3.0,     "SUI"),
        "XAUTUSDT":  (92,  4, 2, 0.003,   "XAUUSDT"),
        "XAUUSDT":   (92,  4, 2, 0.003,   "XAU"),
        "HYPEUSDT":  (24,  2, 4, 0.5,     "HYPE"),
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
    return settings.lighter_aliases.get(symbol, symbol)


# ---------- Rate limit backoff (protected by lock) ----------
_rate_limited_until: float = 0.0  # timestamp when we can resume
_429_count: int = 0
_rate_lock: Optional[asyncio.Lock] = None


def _get_rate_lock() -> asyncio.Lock:
    global _rate_lock
    if _rate_lock is None:
        _rate_lock = asyncio.Lock()
    return _rate_lock


# ---------- Ticker ----------
async def fetch_ticker(symbol: str) -> Optional[NormalizedTick]:
    global _rate_limited_until, _429_count

    # Skip if we're in backoff period
    now = time.time()
    if now < _rate_limited_until:
        return None  # Silently skip during backoff

    lighter_symbol = _resolve_symbol(symbol)
    market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)
    if market_id is None:
        log.warning("lighter_unknown_symbol", symbol=symbol, lighter_symbol=lighter_symbol,
                     available=list(SYMBOL_TO_MARKET_ID.keys())[:10])
        return None

    url = f"{BASE_URL}/api/v1/orderBookOrders"
    params = {"market_id": market_id, "limit": 5}

    try:
        sem = _get_semaphore()
        async with sem:
            session = await _get_session()
            async with session.get(url, params=params) as resp:
                if resp.status == 429:
                    async with _get_rate_lock():
                        _429_count += 1
                        backoff_s = min(2 ** _429_count, 30)
                        _rate_limited_until = time.time() + backoff_s
                    if _429_count <= 3:
                        log.warning("lighter_rate_limited", backoff_s=backoff_s, count=_429_count)
                    return None

                if resp.status != 200:
                    log.error("lighter_ticker_http_error", symbol=symbol, status=resp.status)
                    return None

                # Reset 429 counter on success
                async with _get_rate_lock():
                    _429_count = 0

                data = await resp.json()
                asks = data.get("asks", [])
                bids = data.get("bids", [])

                if not asks or not bids:
                    log.warning("lighter_empty_book", symbol=symbol, market_id=market_id)
                    return None

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


# ---------- Funding rate cache ----------
_funding_cache: Dict[int, Dict] = {}
_funding_cache_ts: float = 0.0
_FUNDING_CACHE_TTL_S = 60.0


async def _refresh_funding_cache():
    global _funding_cache, _funding_cache_ts

    now = time.time()
    if now - _funding_cache_ts < _FUNDING_CACHE_TTL_S and _funding_cache:
        return

    url = f"{BASE_URL}/api/v1/funding-rates"
    try:
        session = await _get_session()
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                log.error("lighter_funding_http_error", status=resp.status)
                # Update timestamp even on error — prevent retry storm
                _funding_cache_ts = now
                return

            data = await resp.json()
            rates = data.get("funding_rates", [])
            if not rates:
                _funding_cache_ts = now
                return

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
        # Update timestamp even on exception — retry after TTL, not immediately
        _funding_cache_ts = now
        log.error("lighter_funding_cache_exception", error=str(e))


async def fetch_funding_rate(symbol: str) -> Optional[FundingSnapshot]:
    lighter_symbol = _resolve_symbol(symbol)
    market_id = SYMBOL_TO_MARKET_ID.get(lighter_symbol)
    if market_id is None:
        return None

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
