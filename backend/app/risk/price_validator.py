from __future__ import annotations

import time
from dataclasses import dataclass

from app.analytics.spread_engine import get_latest_tick
from app.risk.models import OrderRequest


@dataclass(slots=True)
class PriceValidationResult:
    ok: bool
    reason: str
    reference_mid: float


class PriceSanityValidator:
    def validate(self, order: OrderRequest, *, band_pct: float, max_age_s: float) -> PriceValidationResult:
        tick = get_latest_tick(order.exchange, order.symbol)
        if tick is None:
            return PriceValidationResult(False, "no reference tick", 0.0)
        if tick.bid <= 0 or tick.ask <= 0 or tick.mid <= 0:
            return PriceValidationResult(False, "invalid reference book", 0.0)

        tick_ts = tick.received_at or tick.ts
        tick_ts_s = tick_ts / 1000 if tick_ts > 10_000_000_000 else tick_ts
        age_s = time.time() - tick_ts_s
        if age_s > max_age_s:
            return PriceValidationResult(False, f"reference tick stale for {age_s:.2f}s", tick.mid)

        if order.price is None or order.price <= 0:
            return PriceValidationResult(True, "market order uses current book", tick.mid)

        deviation_pct = abs(order.price - tick.mid) / tick.mid * 100
        if deviation_pct > band_pct:
            return PriceValidationResult(
                False,
                f"price deviation {deviation_pct:.3f}% exceeds {band_pct:.3f}%",
                tick.mid,
            )

        return PriceValidationResult(True, "price sanity ok", tick.mid)
