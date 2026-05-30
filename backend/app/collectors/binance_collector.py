import time
from typing import Any

import aiohttp
import structlog

from app.collectors.base import ExchangeAdapter
from app.config import settings
from app.models import NormalizedTick

log = structlog.get_logger()


class BinanceCollector(ExchangeAdapter):
    name = "binance"

    def __init__(self, base_url: str | None = None, symbols: list[str] | None = None):
        self.base_url = (base_url or settings.binance_futures_base_url).rstrip("/")
        self._symbols = symbols or ["XAUTUSDT"]
        self._session: aiohttp.ClientSession | None = None

    @property
    def supported_symbols(self) -> list[str]:
        return self._symbols

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
            )
        return self._session

    async def fetch_ticker(self, symbol: str) -> NormalizedTick | None:
        url = f"{self.base_url}/fapi/v1/ticker/bookTicker"
        params = {"symbol": symbol}
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning("binance_ticker_http_error", symbol=symbol, status=resp.status)
                    return None
                data: dict[str, Any] = await resp.json()

            bid = float(data.get("bidPrice", 0))
            ask = float(data.get("askPrice", 0))
            if bid <= 0 or ask <= 0:
                return None

            return NormalizedTick(
                ts=float(data.get("time") or time.time() * 1000),
                exchange=self.name,
                symbol=str(data.get("symbol") or symbol),
                market_type="perp",
                bid=bid,
                ask=ask,
                bid_size=float(data.get("bidQty", 0)) or None,
                ask_size=float(data.get("askQty", 0)) or None,
                mid=(bid + ask) / 2,
            )
        except Exception as exc:
            log.warning("binance_ticker_error", symbol=symbol, error=str(exc))
            return None

    async def health_check(self) -> dict:
        url = f"{self.base_url}/fapi/v1/ping"
        t0 = time.time()
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
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
