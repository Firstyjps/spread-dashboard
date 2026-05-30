"""
Arbitrage Executor — Sequential Bybit-first execution.

Flow: Bybit PostOnly LIMIT (maker) → wait for fill → Lighter MARKET (exact filled qty).
This guarantees maker fees on Bybit and eliminates position mismatch risk.

Safety: if Lighter fails after Bybit fills, Bybit is reversed immediately.
Cleanup: client resources are properly closed after each execution.
"""
import asyncio
import time
import structlog
from decimal import Decimal
from typing import Optional
from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.collectors.lighter_collector import MARKET_META
from app.execution.maker_engine import smart_execute_maker, MakerConfig, MakerResult
from app.alerts.alert_engine import send_system_alert
from app.analytics.spread_engine import compute_spread
from app.metrics import EXECUTION_DURATION
from app.models import TradeRecord
from app.services.circuit_breaker import circuit_breaker
from app.services.trade_journal import record_trade

log = structlog.get_logger()


def _to_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _build_maker_config(config, force_maker_only: bool = False) -> MakerConfig:
    """Build MakerConfig from app settings."""
    allow_fallback = getattr(config, "maker_allow_market_fallback", True)
    if force_maker_only:
        allow_fallback = False
    return MakerConfig(
        max_time_s=getattr(config, "maker_max_time_s", 15.0),
        reprice_interval_ms=getattr(config, "maker_reprice_interval_ms", 800),
        max_reprices=getattr(config, "maker_max_reprices", 8),
        aggressiveness=getattr(config, "maker_aggressiveness", "BALANCED"),
        allow_market_fallback=allow_fallback,
        maker_fee_rate=getattr(config, "maker_fee_rate", 0.0002),
        taker_fee_rate=getattr(config, "taker_fee_rate", 0.00055),
        spread_guard_ticks=getattr(config, "maker_spread_guard_ticks", 1),
        vol_window=getattr(config, "maker_vol_window", 20),
        vol_limit_ticks=getattr(config, "maker_vol_limit_ticks", 10),
        max_deviation_ticks=getattr(config, "maker_max_deviation_ticks", 50),
    )


class ArbitrageExecutor:
    def __init__(self, config):
        self.config = config
        self.lighter = LighterClient(config)
        self.bybit = BybitClient(config)
        self.maker_only = getattr(config, "arb_maker_only", True)
        self.min_fill_pct = getattr(config, "arb_min_fill_pct", 10.0)
        self.maker_config = _build_maker_config(config, force_maker_only=self.maker_only)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._cleanup()

    async def run_arb(self, symbol: str, strategy_side: str, amount: float):
        """Execute arb: Bybit maker FIRST, then Lighter MARKET with exact filled qty."""
        return await self._run_arb_sequential(symbol, strategy_side, amount)

    # ─── Sequential: Bybit first → Lighter second ────────────────

    async def _run_arb_sequential(self, symbol: str, strategy_side: str, amount: float):
        """Bybit fills as maker, then Lighter matches exact filled qty.

        Flow:
        1. Bybit PostOnly LIMIT via maker engine (no market fallback)
        2. Evaluate: filled / partial / aborted
        3. Lighter MARKET with exact Bybit filled qty
        4. If Lighter fails → reverse Bybit for safety
        """
        start_ms = time.time() * 1000
        spread_bps_at_entry = self._current_spread_bps(symbol)
        failure_counted = False
        log.info("arb_sequential_start", side=strategy_side, symbol=symbol,
                 amount=amount, maker_only=self.maker_only)

        try:
            # Determine sides
            if strategy_side == "BUY_LIGHTER_SELL_BYBIT":
                bybit_side = "Sell"
                lighter_is_ask = False  # buying on Lighter
            else:
                bybit_side = "Buy"
                lighter_is_ask = True   # selling on Lighter

            lighter_preflight_error = await asyncio.to_thread(self.lighter.check_trading_ready)
            if lighter_preflight_error:
                log.error(
                    "arb_seq_lighter_preflight_failed",
                    symbol=symbol,
                    error=lighter_preflight_error,
                )
                bybit_res = MakerResult(
                    status="aborted",
                    filled_qty=Decimal("0"),
                    remaining_qty=Decimal(str(amount)),
                    avg_price=Decimal("0"),
                    estimated_fee=Decimal("0"),
                    detail=lighter_preflight_error,
                )
                await self._record_arb_trade(
                    symbol=symbol,
                    strategy_side=strategy_side,
                    bybit_side=bybit_side,
                    qty_requested=amount,
                    qty_filled=0.0,
                    bybit_res=bybit_res,
                    spread_bps_at_entry=spread_bps_at_entry,
                    start_ms=start_ms,
                    status="aborted",
                    detail=lighter_preflight_error,
                )
                failure_counted = True
                await self._record_execution_failure(
                    f"Lighter preflight failed for {symbol}: {lighter_preflight_error}"
                )
                return [None, bybit_res]

            # ── Phase 1: Bybit maker engine ──
            bybit_res = await smart_execute_maker(
                client=self.bybit,
                symbol=symbol,
                side=bybit_side,
                target_qty=Decimal(str(amount)),
                config=self.maker_config,
            )

            if hasattr(bybit_res, "to_dict"):
                log.info("arb_seq_bybit_result", **bybit_res.to_dict())

            # ── Phase 2: Evaluate Bybit result ──
            if bybit_res.status == "aborted":
                log.warning("arb_seq_bybit_aborted", detail=bybit_res.detail)
                await self._record_arb_trade(
                    symbol=symbol,
                    strategy_side=strategy_side,
                    bybit_side=bybit_side,
                    qty_requested=amount,
                    qty_filled=0.0,
                    bybit_res=bybit_res,
                    spread_bps_at_entry=spread_bps_at_entry,
                    start_ms=start_ms,
                    status="aborted",
                    detail=bybit_res.detail,
                )
                return [None, bybit_res]

            filled_qty = float(bybit_res.filled_qty)
            fill_pct = (filled_qty / amount * 100) if amount > 0 else 0

            # Below minimum fill threshold → reverse and exit
            if filled_qty <= 0 or fill_pct < self.min_fill_pct:
                log.warning("arb_seq_below_threshold",
                            filled_qty=filled_qty, fill_pct=round(fill_pct, 1),
                            threshold_pct=self.min_fill_pct)
                if filled_qty > 0:
                    await self._reverse_bybit(symbol, bybit_side, filled_qty)
                    status = "reversed"
                else:
                    status = "aborted"
                await self._record_arb_trade(
                    symbol=symbol,
                    strategy_side=strategy_side,
                    bybit_side=bybit_side,
                    qty_requested=amount,
                    qty_filled=filled_qty,
                    bybit_res=bybit_res,
                    spread_bps_at_entry=spread_bps_at_entry,
                    start_ms=start_ms,
                    status=status,
                    detail=f"fill {fill_pct:.1f}% below threshold {self.min_fill_pct:.1f}%",
                )
                if filled_qty > 0:
                    failure_counted = True
                    await self._record_execution_failure(
                        f"Bybit fill below threshold for {symbol}; reversed {filled_qty:.6f}"
                    )
                return [None, bybit_res]

            # Check Lighter minimum order size
            lighter_symbol = self.config.lighter_aliases.get(symbol, symbol)
            meta = MARKET_META.get(lighter_symbol, {})
            lighter_min = meta.get("min_base_amount", 0)
            if filled_qty < lighter_min:
                log.warning("arb_seq_below_lighter_min",
                            filled_qty=filled_qty, lighter_min=lighter_min)
                await self._reverse_bybit(symbol, bybit_side, filled_qty)
                await self._record_arb_trade(
                    symbol=symbol,
                    strategy_side=strategy_side,
                    bybit_side=bybit_side,
                    qty_requested=amount,
                    qty_filled=filled_qty,
                    bybit_res=bybit_res,
                    spread_bps_at_entry=spread_bps_at_entry,
                    start_ms=start_ms,
                    status="reversed",
                    detail=f"filled qty {filled_qty:.6f} below Lighter minimum {lighter_min:.6f}",
                )
                failure_counted = True
                await self._record_execution_failure(
                    f"Bybit fill below Lighter minimum for {symbol}; reversed {filled_qty:.6f}"
                )
                return [None, bybit_res]

            # ── Phase 3: Lighter MARKET with exact Bybit filled qty ──
            log.info("arb_seq_lighter_start",
                     lighter_qty=filled_qty, bybit_status=bybit_res.status,
                     bybit_avg_price=str(bybit_res.avg_price))

            try:
                lighter_res = await self.lighter.place_market_order(
                    symbol, filled_qty, is_ask=lighter_is_ask
                )
            except Exception as lighter_err:
                log.error("arb_seq_lighter_failed", error=str(lighter_err),
                          bybit_filled=filled_qty)
                await self._reverse_bybit(symbol, bybit_side, filled_qty)
                await self._record_arb_trade(
                    symbol=symbol,
                    strategy_side=strategy_side,
                    bybit_side=bybit_side,
                    qty_requested=amount,
                    qty_filled=filled_qty,
                    bybit_res=bybit_res,
                    spread_bps_at_entry=spread_bps_at_entry,
                    start_ms=start_ms,
                    status="reversed",
                    detail=f"Lighter failed: {lighter_err}",
                )
                failure_counted = True
                await self._record_execution_failure(
                    f"Lighter failed for {symbol}; Bybit {filled_qty:.6f} {bybit_side} reversed"
                )
                await send_system_alert(
                    "execution_reversal",
                    f"Lighter failed for {symbol}; Bybit {filled_qty:.6f} {bybit_side} reversed",
                    severity="critical",
                )
                raise Exception(
                    f"Lighter failed: {lighter_err}. "
                    f"Bybit position ({filled_qty} {bybit_side}) reversed for safety."
                )

            # ── Phase 4: Success ──
            self._log_fee_savings(symbol, bybit_res, amount, fill_pct)

            log.info("arb_sequential_success",
                     lighter=str(lighter_res), bybit_status=bybit_res.status,
                     matched_qty=filled_qty)

            circuit_breaker.record_execution_success()
            await self._record_arb_trade(
                symbol=symbol,
                strategy_side=strategy_side,
                bybit_side=bybit_side,
                qty_requested=amount,
                qty_filled=filled_qty,
                bybit_res=bybit_res,
                spread_bps_at_entry=spread_bps_at_entry,
                start_ms=start_ms,
                status="partial" if bybit_res.status == "partial" else "success",
                detail=f"Lighter matched Bybit fill; tx={lighter_res.get('tx_hash', 'unknown') if isinstance(lighter_res, dict) else 'unknown'}",
            )
            return [lighter_res, bybit_res]

        except Exception:
            if not failure_counted:
                await self._record_execution_failure(f"Arbitrage execution failed for {symbol}")
            raise
        finally:
            EXECUTION_DURATION.labels(strategy="arb_sequential").observe(
                max(0.0, (time.time() * 1000 - start_ms) / 1000)
            )
            await self._cleanup()

    # ─── Helpers ──────────────────────────────────────────────────

    async def _reverse_bybit(self, symbol: str, original_side: str, qty: float):
        """Reverse a Bybit fill with reduce_only market order."""
        reverse_side = "Buy" if original_side == "Sell" else "Sell"
        try:
            await self.bybit.place_market_order(
                symbol, qty, side=reverse_side, reduce_only=True
            )
            log.info("arb_seq_bybit_reversed", qty=qty, side=reverse_side)
        except Exception as rev_err:
            log.error("arb_seq_reversal_failed_critical", error=str(rev_err),
                      symbol=symbol, side=reverse_side, qty=qty,
                      MANUAL_ACTION_REQUIRED=True)

    def _log_fee_savings(self, symbol: str, bybit_res, amount: float, fill_pct: float):
        """Log maker fee savings vs hypothetical taker execution."""
        if not hasattr(bybit_res, "avg_price"):
            return
        if bybit_res.avg_price <= 0 or bybit_res.filled_qty <= 0:
            return
        taker_cost = float(bybit_res.filled_qty * bybit_res.avg_price) * self.maker_config.taker_fee_rate
        actual_cost = float(bybit_res.estimated_fee)
        saved = taker_cost - actual_cost
        log.info("arb_seq_fee_savings",
                 symbol=symbol,
                 taker_would_cost=round(taker_cost, 4),
                 actual_cost=round(actual_cost, 4),
                 saved_usd=round(saved, 4),
                 fill_rate_pct=round(fill_pct, 1),
                 time_ms=round(bybit_res.time_to_fill_ms, 1),
                 status=bybit_res.status)

    def _current_spread_bps(self, symbol: str) -> Optional[float]:
        spread = compute_spread(symbol)
        if not spread:
            return None
        return spread.exchange_spread_mid * 10_000

    async def _record_execution_failure(self, message: str):
        if circuit_breaker.record_execution_failure():
            await send_system_alert("circuit_breaker_tripped", message, severity="critical")

    async def _record_arb_trade(
        self,
        symbol: str,
        strategy_side: str,
        bybit_side: str,
        qty_requested: float,
        qty_filled: float,
        bybit_res,
        spread_bps_at_entry: Optional[float],
        start_ms: float,
        status: str,
        detail: Optional[str] = None,
    ):
        trade = TradeRecord(
            ts=time.time() * 1000,
            symbol=symbol,
            strategy="arb_sequential",
            side=strategy_side,
            qty_requested=qty_requested,
            qty_filled=qty_filled,
            bybit_side=bybit_side,
            bybit_fill_price=_to_float(getattr(bybit_res, "avg_price", None)),
            bybit_fee=_to_float(getattr(bybit_res, "estimated_fee", None)),
            spread_bps_at_entry=spread_bps_at_entry,
            duration_ms=time.time() * 1000 - start_ms,
            status=status,
            detail=detail,
        )
        await record_trade(trade)

    # ─── Emergency close (unchanged) ─────────────────────────────

    async def emergency_close_both_sides(
        self, symbol: str, lighter_amount: float, bybit_amount: float, lighter_is_long: bool
    ):
        """Close positions on both exchanges."""
        start_ms = time.time() * 1000
        bybit_side = "Sell" if not lighter_is_long else "Buy"
        log.info(
            "emergency_close_triggered",
            symbol=symbol,
            lighter_amt=lighter_amount,
            bybit_amt=bybit_amount,
        )

        tasks = []
        try:
            if lighter_amount > 0:
                tasks.append(
                    self.lighter.place_market_order(
                        symbol=symbol,
                        amount=lighter_amount,
                        is_ask=lighter_is_long,
                        reduce_only=True,
                    )
                )

            if bybit_amount > 0:
                bybit_side = "Sell" if not lighter_is_long else "Buy"
                tasks.append(
                    self.bybit.place_market_order(
                        symbol=symbol,
                        amount=bybit_amount,
                        side=bybit_side,
                        reduce_only=True,
                    )
            )

            if not tasks:
                await self._record_emergency_close(
                    symbol=symbol,
                    lighter_amount=lighter_amount,
                    bybit_amount=bybit_amount,
                    bybit_side=bybit_side,
                    start_ms=start_ms,
                    status="success",
                    detail="No positions to close.",
                )
                circuit_breaker.record_execution_success()
                return {"status": "success", "detail": "No positions to close."}

            results = await asyncio.gather(*tasks, return_exceptions=True)

            errors = [str(r) for r in results if isinstance(r, Exception)]
            if errors:
                await self._record_emergency_close(
                    symbol=symbol,
                    lighter_amount=lighter_amount,
                    bybit_amount=bybit_amount,
                    bybit_side=bybit_side,
                    start_ms=start_ms,
                    status="partial",
                    detail=f"Some closes failed: {'; '.join(errors)}",
                )
                await self._record_execution_failure(f"Emergency close partial for {symbol}")
                return {
                    "status": "partial",
                    "detail": f"Some closes failed: {'; '.join(errors)}",
                    "results": [str(r) for r in results],
                }

            await self._record_emergency_close(
                symbol=symbol,
                lighter_amount=lighter_amount,
                bybit_amount=bybit_amount,
                bybit_side=bybit_side,
                start_ms=start_ms,
                status="success",
                detail="All positions closed.",
            )
            circuit_breaker.record_execution_success()
            return {
                "status": "success",
                "detail": "All positions closed.",
                "results": [str(r) for r in results],
            }

        except Exception as e:
            log.error("emergency_close_failed", error=str(e))
            await self._record_emergency_close(
                symbol=symbol,
                lighter_amount=lighter_amount,
                bybit_amount=bybit_amount,
                bybit_side=bybit_side,
                start_ms=start_ms,
                status="failed",
                detail=f"Close failed: {e}",
            )
            await self._record_execution_failure(f"Emergency close failed for {symbol}")
            return {"status": "failed", "error": f"Close failed: {e}"}

        finally:
            EXECUTION_DURATION.labels(strategy="emergency_close").observe(
                max(0.0, (time.time() * 1000 - start_ms) / 1000)
            )
            await self._cleanup()

    async def emergency_close_auto(self, symbol: str):
        """Auto-detect positions and close them all."""
        log.info("emergency_close_auto_started", symbol=symbol)

        try:
            lighter_pos = await self.lighter.get_position(symbol)
            lighter_amount = lighter_pos.get("amount", 0.0)
            lighter_is_long = lighter_pos.get("is_long", True)

            bybit_pos = await self.bybit.get_position(symbol)
            bybit_amount = bybit_pos.get("amount", 0.0)

            if lighter_amount <= 0 and bybit_amount <= 0:
                await self._record_emergency_close(
                    symbol=symbol,
                    lighter_amount=0.0,
                    bybit_amount=0.0,
                    bybit_side="Buy",
                    start_ms=time.time() * 1000,
                    status="success",
                    detail=f"No open positions found for {symbol}.",
                )
                circuit_breaker.record_execution_success()
                return {"status": "success", "detail": f"No open positions found for {symbol}."}

            log.info(
                "auto_close_amounts_found",
                lighter=lighter_amount,
                lighter_is_long=lighter_is_long,
                bybit=bybit_amount,
            )

            return await self.emergency_close_both_sides(
                symbol=symbol,
                lighter_amount=lighter_amount,
                bybit_amount=bybit_amount,
                lighter_is_long=lighter_is_long,
            )

        except Exception as e:
            log.error("emergency_close_auto_failed", error=str(e))
            await self._record_execution_failure(f"Emergency close auto failed for {symbol}")
            return {"status": "failed", "error": f"Auto-close failed: {str(e)}"}

    async def _cleanup(self):
        """Clean up client resources."""
        try:
            await self.lighter.close()
        except Exception:
            pass

    async def _record_emergency_close(
        self,
        symbol: str,
        lighter_amount: float,
        bybit_amount: float,
        bybit_side: str,
        start_ms: float,
        status: str,
        detail: str,
    ):
        trade = TradeRecord(
            ts=time.time() * 1000,
            symbol=symbol,
            strategy="emergency_close",
            side="close",
            qty_requested=max(float(lighter_amount or 0.0), float(bybit_amount or 0.0)),
            qty_filled=max(float(lighter_amount or 0.0), float(bybit_amount or 0.0)) if status == "success" else 0.0,
            bybit_side=bybit_side,
            duration_ms=time.time() * 1000 - start_ms,
            status=status,
            detail=detail,
        )
        await record_trade(trade)
