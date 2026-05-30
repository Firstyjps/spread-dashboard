from itertools import permutations
from typing import Dict, List, Tuple

from app.collectors.base import ExchangeAdapter
from app.config import settings
from app.models import NormalizedTick

MonitorPair = Tuple[str, str, str, str]
MonitorEntry = Tuple[str, str]


class ExchangeRegistry:
    """Registry for monitor exchange adapters and configured symbol groups."""

    def __init__(self, monitor_groups: str | None = None):
        self.adapters: Dict[str, ExchangeAdapter] = {}
        self._monitor_groups = monitor_groups

    def register(self, adapter: ExchangeAdapter) -> None:
        self.adapters[adapter.name] = adapter

    def get_pairs(self, asset_group: str = "gold") -> List[MonitorPair]:
        """Return all directional (exchange_a, symbol_a, exchange_b, symbol_b) pairs."""
        entries = self.get_group_entries(asset_group)
        if self.adapters:
            entries = [
                (exchange, symbol)
                for exchange, symbol in entries
                if self._is_supported(exchange, symbol)
            ]
        return [
            (exchange_a, symbol_a, exchange_b, symbol_b)
            for (exchange_a, symbol_a), (exchange_b, symbol_b) in permutations(entries, 2)
        ]

    def get_group_entries(self, asset_group: str = "gold") -> List[MonitorEntry]:
        parsed = self._parse_monitor_groups(self._monitor_groups or settings.monitor_groups)
        return parsed.get(asset_group, [])

    def compute_executable_spread(self, tick_a: NormalizedTick, tick_b: NormalizedTick) -> float:
        """Compute executable spread in bps: sell A bid, buy B ask."""
        if tick_b.ask <= 0:
            raise ValueError("tick_b.ask must be positive")
        return (tick_a.bid - tick_b.ask) / tick_b.ask * 10000

    def compute_mid_spread(self, tick_a: NormalizedTick, tick_b: NormalizedTick) -> float:
        if tick_b.mid <= 0:
            raise ValueError("tick_b.mid must be positive")
        return (tick_a.mid - tick_b.mid) / tick_b.mid * 10000

    def compute_buy_spread(self, lighter_tick: NormalizedTick, other_tick: NormalizedTick) -> float:
        """Buy Lighter, sell other: (other_bid - lighter_ask) / lighter_ask in bps."""
        if lighter_tick.ask <= 0:
            raise ValueError("lighter_tick.ask must be positive")
        return (other_tick.bid - lighter_tick.ask) / lighter_tick.ask * 10000

    def compute_sell_spread(self, lighter_tick: NormalizedTick, other_tick: NormalizedTick) -> float:
        """Sell Lighter, buy other: (lighter_bid - other_ask) / other_ask in bps."""
        if other_tick.ask <= 0:
            raise ValueError("other_tick.ask must be positive")
        return (lighter_tick.bid - other_tick.ask) / other_tick.ask * 10000

    def compute_net_spread(self, spread_bps: float, fee_a: float, fee_b: float) -> float:
        return spread_bps - (fee_a + fee_b) * 10000

    def pair_id(self, exchange_a: str, symbol_a: str, exchange_b: str, symbol_b: str) -> str:
        return f"{exchange_a}:{symbol_a}-{exchange_b}:{symbol_b}"

    def _is_supported(self, exchange: str, symbol: str) -> bool:
        adapter = self.adapters.get(exchange)
        if adapter is None:
            return False
        return symbol in adapter.supported_symbols

    @staticmethod
    def _parse_monitor_groups(raw: str) -> dict[str, List[MonitorEntry]]:
        groups: dict[str, List[MonitorEntry]] = {}
        current_group: str | None = None

        for entry in raw.split(","):
            parts = [part.strip() for part in entry.split(":") if part.strip()]
            if len(parts) == 3:
                current_group, exchange, symbol = parts
            elif len(parts) == 2 and current_group:
                exchange, symbol = parts
            else:
                continue

            groups.setdefault(current_group, []).append((exchange.lower(), symbol.upper()))

        return groups
