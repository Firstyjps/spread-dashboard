import time
from typing import Any

import aiohttp
import structlog

from app.collectors.base import ExchangeAdapter
from app.config import settings
from app.models import NormalizedTick

log = structlog.get_logger()


class MexcCollector(ExchangeAdapter):
    name = "mexc"

    def __init__(self, base_url: str | None = None, symbols: list[str] | None = None):
        self.base_url = (base_url or settings.mexc_contract_base_url).rstrip("/")
        self._symbols = symbols or ["XAUT_USDT"]
        self._session: aiohttp.ClientSession | None = None

    @property
    def supported_symbols(self) -> list[str]:
        return self._symbols

    @property
    def fee_maker(self) -> float:
        return 0.0

    @property
    def fee_taker(self) -> float:
        return 0.0001

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
            )
        return self._session

    async def fetch_ticker(self, symbol: str) -> NormalizedTick | None:
        url = f"{self.base_url}/api/v1/contract/ticker"
        params = {"symbol": symbol}
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    log.warning("mexc_ticker_http_error", symbol=symbol, status=resp.status)
                    return None
                data: dict[str, Any] = await resp.json()

            if not data.get("success") or data.get("code") != 0:
                log.warning("mexc_ticker_error_response", symbol=symbol, response=data)
                return None

            payload = data.get("data")
            if isinstance(payload, list):
                payload = next((item for item in payload if item.get("symbol") == symbol), None)
            if not isinstance(payload, dict):
                return None

            return self._parse_ticker(payload, symbol)
        except Exception as exc:
            log.warning("mexc_ticker_error", symbol=symbol, error=str(exc))
            return None

    async def health_check(self) -> dict:
        url = f"{self.base_url}/api/v1/contract/ping"
        t0 = time.time()
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                latency_ms = (time.time() - t0) * 1000
                data = await resp.json(content_type=None)
                ok = resp.status == 200 and bool(data.get("success"))
                return {
                    "exchange": self.name,
                    "status": "ok" if ok else "error",
                    "latency_ms": round(latency_ms, 1),
                    "http_status": resp.status,
                }
        except Exception as exc:
            return {"exchange": self.name, "status": "error", "error": str(exc)}

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    def _parse_ticker(self, data: dict[str, Any], symbol: str) -> NormalizedTick | None:
        bid = float(data.get("bid1", 0) or 0)
        ask = float(data.get("ask1", 0) or 0)
        if bid <= 0 or ask <= 0:
            return None

        return NormalizedTick(
            ts=float(data.get("timestamp") or time.time() * 1000),
            exchange=self.name,
            symbol=str(data.get("symbol") or symbol),
            market_type="perp",
            bid=bid,
            ask=ask,
            mid=(bid + ask) / 2,
            last_price=float(data.get("lastPrice", 0)) or None,
            volume_24h=float(data.get("volume24", 0)) or None,
            open_interest=float(data.get("holdVol", 0)) or None,
        )
