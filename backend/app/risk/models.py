from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

RiskDecisionType = Literal["approve", "reject", "simulate"]
OrderSide = Literal["Buy", "Sell"]


def now_ms() -> float:
    return time.time() * 1000


@dataclass(slots=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    qty: float
    price: float | None
    exchange: str
    order_type: str = "market"
    source: str = "manual"
    timestamp_ms: float = field(default_factory=now_ms)
    reduce_only: bool = False

    def signed_qty(self) -> float:
        return self.qty if self.side == "Buy" else -self.qty

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskConfig:
    dry_run_enabled: bool = True
    max_position_per_symbol: float = 0.1
    position_limits_override: dict[str, float] = field(default_factory=dict)
    max_notional_exposure_usd: float = 10_000.0
    max_order_rate_per_minute: int = 10
    rate_limit_queue_timeout_s: float = 30.0
    price_sanity_band_pct: float = 0.5
    price_data_max_age_s: float = 2.0
    kill_switch_loss_threshold_usd: float = 500.0
    kill_switch_consecutive_failures: int = 3
    kill_switch_feed_stale_s: float = 30.0
    kill_switch_spread_inversion_pct: float = 2.0
    kill_switch_spread_inversion_duration_s: float = 1.0
    cooldown_minutes: float = 5.0
    audit_retention_days: int = 90

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RiskEvaluation:
    decision: RiskDecisionType
    reason: str
    order: OrderRequest
    dry_run_mode: bool
    kill_switch_active: bool
    circuit_breaker_tripped: bool
    cooldown_active: bool
    positions: dict[str, float]
    notional_exposure_usd: float
    order_rates: dict[str, dict[str, float | int | bool]]
    timestamp_ms: float = field(default_factory=now_ms)

    @property
    def approved_for_exchange(self) -> bool:
        return self.decision == "approve"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["order"] = self.order.to_dict()
        return payload


@dataclass(slots=True)
class RiskStateSnapshot:
    dry_run_mode: bool
    kill_switch_active: bool
    kill_switch_reason: str
    circuit_breaker_tripped: bool
    cooldown_active: bool
    cooldown_remaining_s: float
    positions: dict[str, float]
    position_limits: dict[str, float]
    notional_exposure_usd: float
    notional_cap_usd: float
    order_rates: dict[str, dict[str, float | int | bool]]
    config: dict[str, Any]
    last_decision: dict[str, Any] | None
    updated_ts: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RISK_CONFIG_RANGES: dict[str, tuple[float, float]] = {
    "max_position_per_symbol": (0.001, 100.0),
    "max_notional_exposure_usd": (100.0, 10_000_000.0),
    "max_order_rate_per_minute": (1.0, 600.0),
    "rate_limit_queue_timeout_s": (1.0, 300.0),
    "price_sanity_band_pct": (0.01, 50.0),
    "price_data_max_age_s": (0.1, 60.0),
    "kill_switch_loss_threshold_usd": (1.0, 10_000_000.0),
    "kill_switch_consecutive_failures": (1.0, 100.0),
    "kill_switch_feed_stale_s": (1.0, 3600.0),
    "kill_switch_spread_inversion_pct": (0.01, 50.0),
    "kill_switch_spread_inversion_duration_s": (0.1, 3600.0),
    "cooldown_minutes": (1.0, 60.0),
    "audit_retention_days": (1.0, 3650.0),
}
