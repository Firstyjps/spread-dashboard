from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Any

import structlog

from app.analytics.spread_engine import compute_spread, get_latest_tick
from app.config import settings
from app.risk.audit_logger import RiskAuditLogger
from app.risk.circuit_breaker import RiskCircuitBreaker
from app.risk.database import init_risk_db, purge_old_audit_records
from app.risk.kill_switch import KillSwitch
from app.risk.models import OrderRequest, RISK_CONFIG_RANGES, RiskConfig, RiskEvaluation, RiskStateSnapshot, now_ms
from app.risk.notional_calculator import NotionalCalculator
from app.risk.position_tracker import PositionTracker
from app.risk.price_validator import PriceSanityValidator
from app.risk.rate_limiter import OrderRateLimiter
from app.services.circuit_breaker import circuit_breaker as legacy_circuit_breaker

log = structlog.get_logger()


def config_from_settings() -> RiskConfig:
    return RiskConfig(
        dry_run_enabled=settings.risk_dry_run_enabled,
        max_position_per_symbol=settings.risk_max_position_per_symbol,
        position_limits_override=settings.risk_position_limit_overrides,
        max_notional_exposure_usd=settings.risk_max_notional_exposure_usd,
        max_order_rate_per_minute=settings.risk_max_order_rate_per_minute,
        rate_limit_queue_timeout_s=settings.risk_rate_limit_queue_timeout_s,
        price_sanity_band_pct=settings.risk_price_sanity_band_pct,
        price_data_max_age_s=settings.risk_price_data_max_age_s,
        kill_switch_loss_threshold_usd=settings.risk_kill_switch_loss_threshold_usd,
        kill_switch_consecutive_failures=settings.risk_kill_switch_consecutive_failures,
        kill_switch_feed_stale_s=settings.risk_kill_switch_feed_stale_s,
        kill_switch_spread_inversion_pct=settings.risk_kill_switch_spread_inversion_pct,
        kill_switch_spread_inversion_duration_s=settings.risk_kill_switch_spread_inversion_duration_s,
        cooldown_minutes=settings.risk_cooldown_minutes,
        audit_retention_days=settings.risk_audit_retention_days,
    )


class RiskEngine:
    def __init__(self, config: RiskConfig | None = None) -> None:
        self.config = config or config_from_settings()
        self.kill_switch = KillSwitch()
        self.circuit_breaker = RiskCircuitBreaker()
        self.positions = PositionTracker()
        self.notional = NotionalCalculator(self.positions)
        self.price_validator = PriceSanityValidator()
        self.rate_limiter = OrderRateLimiter(
            self.config.max_order_rate_per_minute,
            self.config.rate_limit_queue_timeout_s,
        )
        self.audit = RiskAuditLogger()
        self._lock = asyncio.Lock()
        self._last_decision: dict[str, Any] | None = None
        self._reference_mids: dict[str, float] = {}
        self._consecutive_failures = 0
        self._spread_inversion_started_at: dict[str, float] = {}

    async def initialize(self) -> None:
        await init_risk_db()
        await self.kill_switch.load()
        self.rate_limiter.update_config(
            max_per_minute=self.config.max_order_rate_per_minute,
            timeout_s=self.config.rate_limit_queue_timeout_s,
        )

    async def cleanup(self) -> None:
        await purge_old_audit_records(self.config.audit_retention_days)

    def update_config(self, values: dict[str, Any]) -> RiskConfig:
        allowed = set(self.config.to_dict().keys()) - {"position_limits_override"}
        current = self.config.to_dict()
        for key, value in values.items():
            if key == "position_limits_override":
                current[key] = {str(k).upper(): float(v) for k, v in (value or {}).items()}
                continue
            if key not in allowed:
                continue
            if key in RISK_CONFIG_RANGES:
                low, high = RISK_CONFIG_RANGES[key]
                numeric = float(value)
                if numeric < low or numeric > high:
                    raise ValueError(f"{key} must be between {low} and {high}")
                value = int(numeric) if key in {"max_order_rate_per_minute", "kill_switch_consecutive_failures", "audit_retention_days"} else numeric
            current[key] = value
        self.config = RiskConfig(**current)
        self.rate_limiter.update_config(
            max_per_minute=self.config.max_order_rate_per_minute,
            timeout_s=self.config.rate_limit_queue_timeout_s,
        )
        return self.config

    def reload_from_settings(self) -> RiskConfig:
        self.config = config_from_settings()
        self.rate_limiter.update_config(
            max_per_minute=self.config.max_order_rate_per_minute,
            timeout_s=self.config.rate_limit_queue_timeout_s,
        )
        return self.config

    async def activate_kill_switch(self, reason: str) -> None:
        async with self._lock:
            await self._activate_kill_switch_unlocked(reason)

    async def _activate_kill_switch_unlocked(self, reason: str) -> None:
        await self.kill_switch.activate(reason)
        self.circuit_breaker.trip(reason, self.config.cooldown_minutes)
        self.rate_limiter.discard_all()
        log.warning("risk_kill_switch_activated", reason=reason)

    async def reset_kill_switch(self) -> None:
        async with self._lock:
            await self.kill_switch.reset()
            self.circuit_breaker.reset()
            self.rate_limiter.discard_all()
            self._consecutive_failures = 0
            self._spread_inversion_started_at.clear()
            log.info("risk_kill_switch_reset")

    async def check_feed_health(self, symbol: str, exchanges: tuple[str, ...] = ("bybit", "lighter")) -> None:
        async with self._lock:
            await self._check_feed_health_unlocked(symbol, exchanges)

    async def _check_feed_health_unlocked(self, symbol: str, exchanges: tuple[str, ...] = ("bybit", "lighter")) -> None:
        now = time.time()
        stale: list[str] = []
        for exchange in exchanges:
            tick = get_latest_tick(exchange, symbol)
            if not tick:
                continue
            tick_ts = (tick.received_at or tick.ts) / 1000
            if now - tick_ts > self.config.kill_switch_feed_stale_s:
                stale.append(f"{exchange}:{symbol}:{now - tick_ts:.1f}s")
        if stale:
            await self._activate_kill_switch_unlocked(f"stale feed: {', '.join(stale)}")

    async def check_spread_inversion(self, symbol: str) -> None:
        async with self._lock:
            await self._check_spread_inversion_unlocked(symbol)

    async def _check_spread_inversion_unlocked(self, symbol: str) -> None:
        spread = compute_spread(symbol)
        if not spread:
            self._spread_inversion_started_at.pop(symbol, None)
            return
        threshold = self.config.kill_switch_spread_inversion_pct / 100
        inverted = abs(spread.exchange_spread_mid) >= threshold
        if not inverted:
            self._spread_inversion_started_at.pop(symbol, None)
            return

        started = self._spread_inversion_started_at.setdefault(symbol, time.monotonic())
        if time.monotonic() - started >= self.config.kill_switch_spread_inversion_duration_s:
            await self._activate_kill_switch_unlocked(
                f"spread inversion {spread.exchange_spread_mid * 100:.3f}% on {symbol}"
            )

    async def record_loss(self, pnl_usd: float, reason: str = "loss threshold") -> None:
        if pnl_usd <= -abs(self.config.kill_switch_loss_threshold_usd):
            await self.activate_kill_switch(f"{reason}: {pnl_usd:.2f} USD")

    async def record_execution_result(self, orders: list[OrderRequest], *, success: bool, reason: str = "") -> None:
        async with self._lock:
            if success:
                self._consecutive_failures = 0
                for order in orders:
                    self.positions.record_order_projection(order)
                return

            self._consecutive_failures += 1
            if self._consecutive_failures >= self.config.kill_switch_consecutive_failures:
                await self._activate_kill_switch_unlocked(
                    f"{self._consecutive_failures} consecutive execution failures{': ' + reason if reason else ''}"
                )

    async def evaluate_order(self, order: OrderRequest) -> RiskEvaluation:
        results = await self.evaluate_orders([order])
        return results[0]

    async def evaluate_orders(self, orders: list[OrderRequest]) -> list[RiskEvaluation]:
        if not orders:
            return []

        async with self._lock:
            for order in orders:
                await self._run_auto_checks_unlocked(order.symbol)

            reject_reason = self._global_reject_reason()
            if reject_reason:
                return await self._decide_all(orders, "reject", reject_reason)

            validation = self._validate_batch(orders)
            if validation:
                return await self._decide_all(orders, "reject", validation)

            if self.config.dry_run_enabled:
                return await self._decide_all(orders, "simulate", "dry-run mode active")

            for order in orders:
                acquired = await self.rate_limiter.acquire(order.exchange)
                if not acquired:
                    return await self._decide_all(orders, "reject", f"order rate limit timeout on {order.exchange}")

            return await self._decide_all(orders, "approve", "risk checks passed")

    async def _run_auto_checks_unlocked(self, symbol: str) -> None:
        await self._check_feed_health_unlocked(symbol)
        await self._check_spread_inversion_unlocked(symbol)
        if legacy_circuit_breaker.is_tripped:
            self.circuit_breaker.trip("legacy circuit breaker tripped", self.config.cooldown_minutes)

    def _global_reject_reason(self) -> str | None:
        if self.kill_switch.active:
            return f"kill switch active: {self.kill_switch.reason}"
        if legacy_circuit_breaker.is_tripped:
            return "legacy circuit breaker tripped"
        if self.circuit_breaker.is_cooldown_active():
            return f"circuit breaker cooldown active ({self.circuit_breaker.cooldown_remaining_s():.0f}s remaining)"
        return None

    def _validate_batch(self, orders: list[OrderRequest]) -> str | None:
        projected = self.positions.get_exchange_positions()
        reference_mids = dict(self._reference_mids)

        for order in orders:
            if order.qty <= 0 and not order.reduce_only:
                return f"{order.exchange} {order.symbol}: qty must be positive"

            price_check = self.price_validator.validate(
                order,
                band_pct=self.config.price_sanity_band_pct,
                max_age_s=self.config.price_data_max_age_s,
            )
            if not price_check.ok:
                return f"{order.exchange} {order.symbol}: {price_check.reason}"

            reference_mids[order.symbol] = price_check.reference_mid
            exchange_positions = projected.setdefault(order.symbol, {})
            current = exchange_positions.get(order.exchange, 0.0)
            next_qty = current + order.signed_qty()
            if abs(next_qty) < 1e-12:
                exchange_positions.pop(order.exchange, None)
            else:
                exchange_positions[order.exchange] = next_qty
            if not exchange_positions:
                projected.pop(order.symbol, None)

            limit = self.positions.position_limit_for(
                order.symbol.upper(),
                self.config.max_position_per_symbol,
                self.config.position_limits_override,
            )
            gross = sum(abs(qty) for qty in projected.get(order.symbol, {}).values())
            if gross > limit and not order.reduce_only:
                return f"{order.symbol} gross position {gross:.8f} exceeds limit {limit:.8f}"

            exposure = 0.0
            for symbol, exchanges in projected.items():
                mid = reference_mids.get(symbol)
                if mid and mid > 0:
                    exposure += sum(abs(qty) for qty in exchanges.values()) * mid
            if exposure > self.config.max_notional_exposure_usd and not order.reduce_only:
                return f"notional exposure {exposure:.2f} exceeds cap {self.config.max_notional_exposure_usd:.2f}"

        self._reference_mids = reference_mids
        return None

    async def _decide_all(self, orders: list[OrderRequest], decision: str, reason: str) -> list[RiskEvaluation]:
        results = [self._build_evaluation(order, decision, reason) for order in orders]
        for evaluation in results:
            await self.audit.log(evaluation)
            self._last_decision = evaluation.to_dict()
        return results

    def _build_evaluation(self, order: OrderRequest, decision: str, reason: str) -> RiskEvaluation:
        return RiskEvaluation(
            decision=decision,  # type: ignore[arg-type]
            reason=reason,
            order=order,
            dry_run_mode=self.config.dry_run_enabled,
            kill_switch_active=self.kill_switch.active,
            circuit_breaker_tripped=self.circuit_breaker.tripped or legacy_circuit_breaker.is_tripped,
            cooldown_active=self.circuit_breaker.is_cooldown_active(),
            positions=self.positions.get_gross_positions(),
            notional_exposure_usd=self.notional.compute_total_exposure(self._reference_mids),
            order_rates=self.rate_limiter.get_rate_status(),
        )

    def snapshot(self) -> RiskStateSnapshot:
        return RiskStateSnapshot(
            dry_run_mode=self.config.dry_run_enabled,
            kill_switch_active=self.kill_switch.active,
            kill_switch_reason=self.kill_switch.reason,
            circuit_breaker_tripped=self.circuit_breaker.tripped or legacy_circuit_breaker.is_tripped,
            cooldown_active=self.circuit_breaker.is_cooldown_active(),
            cooldown_remaining_s=self.circuit_breaker.cooldown_remaining_s(),
            positions=self.positions.get_gross_positions(),
            position_limits={
                symbol: self.positions.position_limit_for(
                    symbol,
                    self.config.max_position_per_symbol,
                    self.config.position_limits_override,
                )
                for symbol in set(self.positions.get_gross_positions()) | set(self.config.position_limits_override)
            },
            notional_exposure_usd=self.notional.compute_total_exposure(self._reference_mids),
            notional_cap_usd=self.config.max_notional_exposure_usd,
            order_rates=self.rate_limiter.get_rate_status(),
            config=self.config.to_dict(),
            last_decision=self._last_decision,
            updated_ts=now_ms(),
        )

    def clone_config_with(self, **values: Any) -> RiskConfig:
        return replace(self.config, **values)


_risk_engine: RiskEngine | None = None


def get_risk_engine() -> RiskEngine:
    global _risk_engine
    if _risk_engine is None:
        _risk_engine = RiskEngine()
    return _risk_engine
