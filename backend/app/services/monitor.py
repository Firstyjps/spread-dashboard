import asyncio
import time
from collections import defaultdict, deque
from typing import Any

import structlog

from app.collectors.aster_collector import AsterCollector
from app.collectors.binance_collector import BinanceCollector
from app.collectors.bybit_collector import BybitCollector
from app.collectors.grvt_collector import GrvtCollector
from app.collectors.lighter_collector import LighterCollector
from app.collectors.registry import ExchangeRegistry, MonitorPair
from app.models import NormalizedTick

log = structlog.get_logger()


class MonitorService:
    def __init__(self, registry: ExchangeRegistry | None = None, history_limit: int = 10_000):
        self.registry = registry or self._build_default_registry()
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(lambda: deque(maxlen=history_limit))
        self._latest_snapshot: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    def get_pairs(self, group: str = "gold") -> list[dict[str, Any]]:
        return [
            {
                "id": self.registry.pair_id(exchange_a, symbol_a, exchange_b, symbol_b),
                "exchange_a": exchange_a,
                "symbol_a": symbol_a,
                "exchange_b": exchange_b,
                "symbol_b": symbol_b,
            }
            for exchange_a, symbol_a, exchange_b, symbol_b in self.registry.get_pairs(group)
        ]

    async def fetch_current_spreads(self, group: str = "gold", store_history: bool = False) -> dict[str, Any]:
        pairs = self.registry.get_pairs(group)
        ts = time.time() * 1000
        ticks = await self._fetch_ticks(pairs)

        spread_rows: list[dict[str, Any]] = []
        for exchange_a, symbol_a, exchange_b, symbol_b in pairs:
            tick_a = ticks.get((exchange_a, symbol_a))
            tick_b = ticks.get((exchange_b, symbol_b))
            if tick_a is None or tick_b is None:
                continue

            pair_id = self.registry.pair_id(exchange_a, symbol_a, exchange_b, symbol_b)
            try:
                row = {
                    "id": pair_id,
                    "exchange_a": exchange_a,
                    "symbol_a": symbol_a,
                    "price_a": self._price_payload(tick_a),
                    "exchange_b": exchange_b,
                    "symbol_b": symbol_b,
                    "price_b": self._price_payload(tick_b),
                    "executable_spread_bps": round(self.registry.compute_executable_spread(tick_a, tick_b), 4),
                    "mid_spread_bps": round(self.registry.compute_mid_spread(tick_a, tick_b), 4),
                    "direction": "sell_a_buy_b",
                    "ts": ts,
                }
            except ValueError as exc:
                log.warning("monitor_spread_compute_error", pair_id=pair_id, error=str(exc))
                continue
            spread_rows.append(row)

        snapshot = {"group": group, "ts": ts, "pairs": spread_rows}
        if store_history:
            async with self._lock:
                self._latest_snapshot = snapshot
                for row in spread_rows:
                    self._history[row["id"]].append(row)
        return snapshot

    async def get_history(self, pair: str, minutes: int = 60) -> list[dict[str, Any]]:
        cutoff = time.time() * 1000 - minutes * 60_000
        async with self._lock:
            return [row for row in self._history.get(pair, []) if row.get("ts", 0) >= cutoff]

    async def latest_snapshot(self) -> dict[str, Any] | None:
        async with self._lock:
            return self._latest_snapshot

    async def close(self) -> None:
        await asyncio.gather(
            *(adapter.close() for adapter in self.registry.adapters.values()),
            return_exceptions=True,
        )

    async def _fetch_ticks(self, pairs: list[MonitorPair]) -> dict[tuple[str, str], NormalizedTick]:
        targets = sorted({(ex_a, sym_a) for ex_a, sym_a, _, _ in pairs} | {(ex_b, sym_b) for _, _, ex_b, sym_b in pairs})
        tasks = [self._fetch_tick(exchange, symbol) for exchange, symbol in targets]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        ticks: dict[tuple[str, str], NormalizedTick] = {}
        for target, result in zip(targets, results):
            if isinstance(result, NormalizedTick):
                ticks[target] = result
            elif isinstance(result, Exception):
                log.warning("monitor_tick_fetch_exception", target=target, error=str(result))
        return ticks

    async def _fetch_tick(self, exchange: str, symbol: str) -> NormalizedTick | None:
        adapter = self.registry.adapters.get(exchange)
        if adapter is None:
            return None
        return await adapter.fetch_ticker(symbol)

    def _build_default_registry(self) -> ExchangeRegistry:
        registry = ExchangeRegistry()
        for adapter in (
            BybitCollector(),
            BinanceCollector(),
            LighterCollector(),
            GrvtCollector(),
            AsterCollector(),
        ):
            registry.register(adapter)
        return registry

    def _price_payload(self, tick: NormalizedTick) -> dict[str, float]:
        return {"bid": tick.bid, "ask": tick.ask, "mid": tick.mid}


_monitor_service: MonitorService | None = None


def get_monitor_service() -> MonitorService:
    global _monitor_service
    if _monitor_service is None:
        _monitor_service = MonitorService()
    return _monitor_service
