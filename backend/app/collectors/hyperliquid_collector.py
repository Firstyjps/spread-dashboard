import time
from typing import Any

import aiohttp
import structlog

from app.collectors.base import ExchangeAdapter
from app.config import settings
from app.models import NormalizedTick

log = structlog.get_logger()


class HyperliquidCollector(ExchangeAdapter):
    name = "hyperliquid"

    def __init__(self, info_url: str | None = None, symbols: list[str] | None = None):
        self.info_url = info_url or settings.hyperliquid_info_url
        self._symbols = symbols or ["XAU"]
        self._session: aiohttp.ClientSession | None = None

    @property
    def supported_symbols(self) -> list[str]:
        return self._symbols

    @property
    def fee_maker(self) -> float:
        return 0.00015

    @property
    def fee_taker(self) -> float:
        return 0.00045

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300),
            )
        return self._session

    async def fetch_ticker(self, symbol: str) -> NormalizedTick | None:
        payload = {"type": "l2Book", "coin": symbol.upper()}
        try:
            session = await self._get_session()
            async with session.post(self.info_url, json=payload) as resp:
                if resp.status != 200:
                    log.warning("hyperliquid_book_http_error", symbol=symbol, status=resp.status)
                    return None
                data: dict[str, Any] = await resp.json()

            levels = data.get("levels") or []
            if len(levels) < 2 or not levels[0] or not levels[1]:
                return None

            best_bid = levels[0][0]
            best_ask = levels[1][0]
            bid = float(best_bid.get("px", 0))
            ask = float(best_ask.get("px", 0))
            if bid <= 0 or ask <= 0:
                return None

            return NormalizedTick(
                ts=float(data.get("time") or time.time() * 1000),
                exchange=self.name,
                symbol=symbol.upper(),
                market_type="perp",
                bid=bid,
                ask=ask,
                bid_size=float(best_bid.get("sz", 0)) or None,
                ask_size=float(best_ask.get("sz", 0)) or None,
                mid=(bid + ask) / 2,
            )
        except Exception as exc:
            log.warning("hyperliquid_book_error", symbol=symbol, error=str(exc))
            return None

    async def health_check(self) -> dict:
        t0 = time.time()
        try:
            session = await self._get_session()
            async with session.post(self.info_url, json={"type": "meta"}) as resp:
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
