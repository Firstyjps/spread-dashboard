import time
from typing import Any

import aiohttp
import structlog

from app.collectors.base import ExchangeAdapter
from app.config import settings
from app.models import NormalizedTick

log = structlog.get_logger()


class GrvtCollector(ExchangeAdapter):
    name = "grvt"

    def __init__(self, base_url: str | None = None, symbols: list[str] | None = None):
        self.base_url = (base_url or settings.grvt_market_data_base_url).rstrip("/")
        self._symbols = symbols or ["XAU", "PAXG"]
        self._session: aiohttp.ClientSession | None = None

    @property
    def supported_symbols(self) -> list[str]:
        return self._symbols

    @property
    def fee_taker(self) -> float:
        return 0.0005

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
            )
        return self._session

    async def fetch_ticker(self, symbol: str) -> NormalizedTick | None:
        url = f"{self.base_url}/full/v1/book"
        payload = {"instrument": self._to_instrument(symbol), "depth": 1}
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    log.warning("grvt_book_http_error", symbol=symbol, status=resp.status)
                    return None
                data: dict[str, Any] = await resp.json()

            result = data.get("result") or {}
            bids = result.get("bids") or []
            asks = result.get("asks") or []
            if not bids or not asks:
                return None

            best_bid = bids[0]
            best_ask = asks[0]
            bid = float(best_bid.get("price", 0))
            ask = float(best_ask.get("price", 0))
            if bid <= 0 or ask <= 0:
                return None

            return NormalizedTick(
                ts=self._event_time_ms(result.get("event_time")),
                exchange=self.name,
                symbol=symbol,
                market_type="perp",
                bid=bid,
                ask=ask,
                bid_size=float(best_bid.get("size", 0)) or None,
                ask_size=float(best_ask.get("size", 0)) or None,
                mid=(bid + ask) / 2,
            )
        except Exception as exc:
            log.warning("grvt_book_error", symbol=symbol, error=str(exc))
            return None

    async def health_check(self) -> dict:
        url = f"{self.base_url}/full/v1/instruments"
        t0 = time.time()
        try:
            session = await self._get_session()
            async with session.post(url, json={"is_active": True, "limit": 1}) as resp:
                latency_ms = (time.time() - t0) * 1000
                return {
                    "exchange": self.name,
                    "status": "ok" if resp.status == 200 else "error",
                    "latency_ms": round(latency_ms, 1),
                    "http_status": resp.status,
                }
        except Exception as exc:
            return {"exchange": self.name, "status": "error", "error": str(exc)}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def _to_instrument(self, symbol: str) -> str:
        normalized = symbol.upper().replace("-", "").replace("/", "")
        if normalized.endswith("USDT"):
            base = normalized.removesuffix("USDT")
        else:
            base = normalized
        return f"{base}_USDT_Perp"

    def _event_time_ms(self, event_time: Any) -> float:
        try:
            raw = float(event_time)
        except (TypeError, ValueError):
            return time.time() * 1000
        if raw > 1_000_000_000_000_000:
            return raw / 1_000_000
        if raw > 1_000_000_000_000:
            return raw
        return raw * 1000
