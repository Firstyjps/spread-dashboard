from __future__ import annotations

from collections import defaultdict

from app.risk.models import OrderRequest


class PositionTracker:
    def __init__(self) -> None:
        self._positions: dict[str, dict[str, float]] = defaultdict(dict)

    def set_exchange_positions(self, positions: dict[str, dict[str, float]]) -> None:
        self._positions = defaultdict(dict)
        for symbol, exchanges in positions.items():
            for exchange, qty in exchanges.items():
                if abs(qty) >= 1e-12:
                    self._positions[symbol][exchange] = qty

    def update_position(self, symbol: str, side: str, qty: float, exchange: str) -> None:
        signed = qty if side == "Buy" else -qty
        current = self._positions[symbol].get(exchange, 0.0)
        next_qty = current + signed
        if abs(next_qty) < 1e-12:
            self._positions[symbol].pop(exchange, None)
        else:
            self._positions[symbol][exchange] = next_qty
        if not self._positions[symbol]:
            self._positions.pop(symbol, None)

    def record_order_projection(self, order: OrderRequest) -> None:
        self.update_position(order.symbol, order.side, order.qty, order.exchange)

    def project_exchange_positions(self, order: OrderRequest) -> dict[str, dict[str, float]]:
        positions = self.get_exchange_positions()
        exchange_positions = positions.setdefault(order.symbol, {})
        current = exchange_positions.get(order.exchange, 0.0)
        next_qty = current + order.signed_qty()
        if abs(next_qty) < 1e-12:
            exchange_positions.pop(order.exchange, None)
        else:
            exchange_positions[order.exchange] = next_qty
        if not exchange_positions:
            positions.pop(order.symbol, None)
        return positions

    def get_net_position(self, symbol: str) -> float:
        return sum(self._positions.get(symbol, {}).values())

    def get_all_positions(self) -> dict[str, float]:
        return {symbol: sum(exchanges.values()) for symbol, exchanges in self._positions.items()}

    def get_symbol_gross_position(self, symbol: str) -> float:
        return sum(abs(qty) for qty in self._positions.get(symbol, {}).values())

    def get_gross_positions(self) -> dict[str, float]:
        return {symbol: sum(abs(qty) for qty in exchanges.values()) for symbol, exchanges in self._positions.items()}

    def get_exchange_positions(self) -> dict[str, dict[str, float]]:
        return {symbol: dict(exchanges) for symbol, exchanges in self._positions.items()}

    def position_limit_for(self, symbol: str, default_limit: float, overrides: dict[str, float]) -> float:
        return overrides.get(symbol, default_limit)

    def would_reduce_position(self, order: OrderRequest) -> bool:
        current = self._positions.get(order.symbol, {}).get(order.exchange, 0.0)
        projected = current + order.signed_qty()
        return abs(projected) < abs(current)

    def would_exceed_limit(self, order: OrderRequest, limit: float) -> bool:
        projected = self.project_exchange_positions(order)
        gross = sum(abs(qty) for qty in projected.get(order.symbol, {}).values())
        return gross > limit
