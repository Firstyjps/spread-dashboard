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
    global SYMBOL_TO_MARKET_ID, MARKET_ID_TO_SYMBOL, LIGHTER_SYM_TO_NORMALIZED

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
    """Fallback mapping based on verified data (2026-03-01)."""
    global SYMBOL_TO_MARKET_ID, MARKET_ID_TO_SYMBOL, LIGHTER_SYM_TO_NORMALIZED
    log.warning("lighter_using_fallback_market_ids")
    SYMBOL_TO_MARKET_ID = {"ETHUSDT": 0, "BTCUSDT": 1, "SOLUSDT": 2, "DOGEUSDT": 3}
    MARKET_ID_TO_SYMBOL = {0: "ETHUSDT", 1: "BTCUSDT", 2: "SOLUSDT", 3: "DOGEUSDT"}
    LIGHTER_SYM_TO_NORMALIZED = {"ETH": "ETHUSDT", "BTC": "BTCUSDT", "SOL": "SOLUSDT", "DOGE": "DOGEUSDT"}


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
    market_id = SYMBOL_TO_MARKET_ID.get(symbol)
    if market_id is None:
        log.warning("lighter_unknown_symbol", symbol=symbol, available=list(SYMBOL_TO_MARKET_ID.keys()))
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


async def fetch_funding_rate(symbol: str) -> Optional[FundingSnapshot]:
    """
    Fetch funding rate from Lighter cross-exchange funding endpoint.
    Endpoint: GET /api/v1/funding-rates
    Response: {
      "code": 200,
      "funding_rates": [
        {"market_id": 1, "exchange": "lighter", "symbol": "BTC", "rate": 0.00012},
        {"market_id": 1, "exchange": "bybit", "symbol": "BTC", "rate": 0.00015},
        ...
      ]
    }
    We filter for exchange="lighter" and matching symbol.
    """
    market_id = SYMBOL_TO_MARKET_ID.get(symbol)
    if market_id is None:
        return None

    url = f"{BASE_URL}/api/v1/funding-rates"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    log.error("lighter_funding_http_error", status=resp.status)
                    return None

                data = await resp.json()
                rates = data.get("funding_rates", [])

                # Find the lighter rate for our market_id
                lighter_rate = None
                for r in rates:
                    if r.get("exchange") == "lighter" and r.get("market_id") == market_id:
                        lighter_rate = r
                        break

                if lighter_rate is None:
                    log.debug("lighter_no_funding_for_market", symbol=symbol, market_id=market_id)
                    return None

                rate = float(lighter_rate["rate"])
                # Lighter funding interval: assumed 1h (ต้องตรวจสอบจาก docs ถ้าเปลี่ยน)
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
        log.error("lighter_funding_exception", symbol=symbol, error=str(e))
        return None
