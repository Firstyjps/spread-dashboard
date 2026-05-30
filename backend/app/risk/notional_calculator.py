from __future__ import annotations

from app.risk.models import OrderRequest
from app.risk.position_tracker import PositionTracker


class NotionalCalculator:
    def __init__(self, positions: PositionTracker) -> None:
        self.positions = positions

    def compute_total_exposure(self, reference_mids: dict[str, float]) -> float:
        total = 0.0
        for symbol, exchanges in self.positions.get_exchange_positions().items():
            mid = reference_mids.get(symbol)
            if mid and mid > 0:
                total += sum(abs(position) for position in exchanges.values()) * mid
        return total

    def projected_total_exposure(self, order: OrderRequest, reference_mid: float, reference_mids: dict[str, float]) -> float:
        positions = self.positions.project_exchange_positions(order)

        total = 0.0
        for symbol, exchanges in positions.items():
            mid = reference_mid if symbol == order.symbol else reference_mids.get(symbol)
            if mid and mid > 0:
                total += sum(abs(position) for position in exchanges.values()) * mid
        return total

    def would_exceed_cap(
        self,
        order: OrderRequest,
        reference_mid: float,
        cap: float,
        reference_mids: dict[str, float],
    ) -> bool:
        return self.projected_total_exposure(order, reference_mid, reference_mids) > cap
