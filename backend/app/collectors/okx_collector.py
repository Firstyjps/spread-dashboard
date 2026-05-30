import time
from typing import Any

import aiohttp
import structlog

from app.collectors.base import ExchangeAdapter
from app.config import settings
from app.models import NormalizedTick

log = structlog.get_logger()


class OkxCollector(ExchangeAdapter):
    name = "okx"

    def __init__(self, base_url: str | None = None, symbols: list[str] | None = None):
        self.base_url = (base_url or settings.okx_base_url).rstrip("/")
        self._symbols = symbols or ["XAUT-USDT-SWAP"]
        self._session: aiohttp.ClientSession | None = None

    @property
    def supported_symbols(self) -> list[str]:
        return self._symbols

    @property
    def fee_maker(self) -> float:
        return 0.0002

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
        url = f"{self.base_url}/api/v5/market/ticker"
        params = {"instId": symbol}
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning("okx_ticker_http_error", symbol=symbol, status=resp.status)
                    return None
                data: dict[str, Any] = await resp.json()

            if data.get("code") != "0":
                log.warning("okx_ticker_error_response", symbol=symbol, response=data)
                return None

            items = data.get("data") or []
            if not items:
                return None
            ticker = items[0]
            bid = float(ticker.get("bidPx", 0))
            ask = float(ticker.get("askPx", 0))
            if bid <= 0 or ask <= 0:
                return None

            return NormalizedTick(
                ts=float(ticker.get("ts") or time.time() * 1000),
                exchange=self.name,
                symbol=str(ticker.get("instId") or symbol),
                market_type="perp",
                bid=bid,
                ask=ask,
                bid_size=float(ticker.get("bidSz", 0)) or None,
                ask_size=float(ticker.get("askSz", 0)) or None,
                mid=(bid + ask) / 2,
                last_price=float(ticker.get("last", 0)) or None,
                volume_24h=float(ticker.get("vol24h", 0)) or None,
            )
        except Exception as exc:
            log.warning("okx_ticker_exception", symbol=symbol, error=str(exc))
            return None

    async def health_check(self) -> dict:
        url = f"{self.base_url}/api/v5/public/time"
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
