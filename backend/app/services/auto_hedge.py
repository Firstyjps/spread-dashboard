"""
Auto-Hedge Service — monitors Bybit position and keeps Lighter hedged.

Safety guarantees:
  1. POST-HEDGE LOCKOUT: After any successful hedge, waits POST_HEDGE_WAIT_S
     for Lighter to reflect the new position before re-polling. Prevents
     double-firing while Lighter API is still showing stale data.
  2. IN-FLIGHT LOCK: Only one hedge order can be executing at a time.
     Uses asyncio.Lock so concurrent polls cannot race each other.
  3. AMOUNT CAP: Never hedges more than |bybit_position| in one order.
     Even if net_delta is huge, the cap prevents runaway overshooting.
  4. EXPONENTIAL BACKOFF on failures (429 / network errors): 5s → 10s →
     20s → … → 300s max. Resets to 5s on next success.
  5. MAX CONSECUTIVE ERRORS: If > MAX_CONSECUTIVE_ERRORS consecutive poll
     errors occur, the service stops itself and logs a critical alert.
  6. RECONCILIATION-BASED LOGIC: Computes net_delta = bybit_qty + lighter_qty
     every cycle so mismatches are corrected even after a restart.
"""
import asyncio
import time
import structlog
from typing import Optional

from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.config import settings
from app.models import TradeRecord
from app.services.trade_journal import record_trade
from app.analytics.spread_engine import get_all_current_data

log = structlog.get_logger()

MAX_HEDGE_LOG = 100
MAX_CONSECUTIVE_ERRORS = 15    # Stop self if this many poll errors in a row
POST_HEDGE_WAIT_S = 6.0        # Wait after success before next poll (Lighter API lag)
INITIAL_COOLDOWN_S = 5.0       # Starting retry cooldown after failure
MAX_COOLDOWN_S = 300.0         # Max cooldown (5 minutes)


class AutoHedgeService:
    def __init__(self):
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._symbol: str = ""
        self._poll_interval_s: float = 2.0
        self._min_delta: float = 0.001

        # Cooldown / backoff state
        self._last_failed_ts: float = 0.0
        self._cooldown_s: float = INITIAL_COOLDOWN_S
        self._last_hedge_ts: float = 0.0   # ts of last SUCCESSFUL hedge

        # Stats
        self._consecutive_errors: int = 0
        self._hedges_executed: int = 0
        self._hedge_log: list[dict] = []
        self._started_at: Optional[float] = None

        # Clients / concurrency
        self._bybit: Optional[BybitClient] = None
        self._lighter: Optional[LighterClient] = None
        self._lock = asyncio.Lock()           # Prevents concurrent hedge execution

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _to_signed(self, pos: dict) -> float:
        """Convert position dict to signed float (+long, -short)."""
        amount = float(pos.get("amount", 0.0) or 0.0)
        if amount == 0:
            return 0.0
        return amount if pos.get("is_long", True) else -amount

    # ─── Main poll loop ───────────────────────────────────────────────────

    async def _poll_loop(self):
        while self._running:
            try:
                # ── 1. Fetch both positions concurrently ──────────────────
                bybit_pos, lighter_pos = await asyncio.wait_for(
                    asyncio.gather(
                        self._bybit.get_position(self._symbol),
                        self._lighter.get_position(self._symbol),
                    ),
                    timeout=10.0,
                )

                bybit_qty   = self._to_signed(bybit_pos)
                lighter_qty = self._to_signed(lighter_pos)
                net_delta   = bybit_qty + lighter_qty   # 0 = perfectly hedged

                self._consecutive_errors = 0

                log.debug(
                    "auto_hedge_poll",
                    symbol=self._symbol,
                    bybit=round(bybit_qty, 6),
                    lighter=round(lighter_qty, 6),
                    net_delta=round(net_delta, 6),
                )

                # ── 2. Check if we need to act ────────────────────────────
                if abs(net_delta) >= self._min_delta:

                    # 2a. POST-HEDGE LOCKOUT — give Lighter time to update
                    now = time.time()
                    since_last_hedge = now - self._last_hedge_ts
                    if since_last_hedge < POST_HEDGE_WAIT_S:
                        wait_remaining = POST_HEDGE_WAIT_S - since_last_hedge
                        log.debug(
                            "auto_hedge_post_hedge_lockout",
                            wait_remaining=round(wait_remaining, 1),
                        )
                        await asyncio.sleep(min(wait_remaining, self._poll_interval_s))
                        continue

                    # 2b. FAILURE COOLDOWN — backoff after 429 / errors
                    since_last_fail = now - self._last_failed_ts
                    if since_last_fail < self._cooldown_s:
                        wait_remaining = self._cooldown_s - since_last_fail
                        log.debug(
                            "auto_hedge_cooldown_wait",
                            wait_remaining=round(wait_remaining, 1),
                            cooldown_s=self._cooldown_s,
                        )
                        await asyncio.sleep(min(wait_remaining, self._poll_interval_s))
                        continue

                    # 2c. AMOUNT CAP — never overshoot bybit position size
                    max_hedge = abs(bybit_qty)
                    raw_amount = abs(net_delta)
                    capped_amount = min(raw_amount, max_hedge)

                    if capped_amount < self._min_delta:
                        log.debug("auto_hedge_cap_too_small", capped=capped_amount)
                        await asyncio.sleep(self._poll_interval_s)
                        continue

                    # 2d. Execute hedge (guarded by lock)
                    await self._execute_hedge(
                        net_delta=net_delta,
                        amount=capped_amount,
                        bybit_qty=bybit_qty,
                        bybit_pos=bybit_pos,
                    )

            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                self._consecutive_errors += 1
                log.warning(
                    "auto_hedge_poll_timeout",
                    consecutive=self._consecutive_errors,
                )
            except Exception as e:
                self._consecutive_errors += 1
                log.error(
                    "auto_hedge_poll_error",
                    error=str(e),
                    consecutive=self._consecutive_errors,
                )

            # ── 3. Auto-stop if too many errors in a row ──────────────────
            if self._consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                log.critical(
                    "auto_hedge_self_stopping",
                    reason="too_many_consecutive_errors",
                    count=self._consecutive_errors,
                )
                self._running = False
                return

            await asyncio.sleep(self._poll_interval_s)

    # ─── Execute a single hedge order ─────────────────────────────────────

    async def _execute_hedge(
        self,
        net_delta: float,
        amount: float,
        bybit_qty: float,
        bybit_pos: dict,
    ):
        """Place ONE hedge order on Lighter (lock prevents concurrent calls)."""
        # If another coroutine is already inside, skip — don't queue up
        if self._lock.locked():
            log.debug("auto_hedge_skip_locked")
            return

        async with self._lock:
            is_ask   = net_delta > 0   # net positive → sell on Lighter
            side_str = "SELL" if is_ask else "BUY"

            log.info(
                "auto_hedge_executing",
                symbol=self._symbol,
                net_delta=round(net_delta, 6),
                amount=round(amount, 6),
                lighter_side=side_str,
            )

            entry = {
                "ts":           time.time(),
                "symbol":       self._symbol,
                "net_delta":    round(net_delta, 6),
                "lighter_side": side_str,
                "amount":       amount,
                "status":       "pending",
            }

            bybit_entry_price = float(bybit_pos.get("entry_price", 0.0))
            spread_data = get_all_current_data().get(self._symbol, {})
            spread_bps_at_entry = (
                spread_data.get("exchange_spread_mid", 0) * 10000
                if spread_data.get("exchange_spread_mid") else None
            )

            try:
                result = await self._lighter.place_market_order(
                    symbol=self._symbol,
                    amount=amount,
                    is_ask=is_ask,
                )

                # ── SUCCESS ───────────────────────────────────────────────
                self._last_hedge_ts = time.time()   # Start post-hedge lockout
                self._cooldown_s    = INITIAL_COOLDOWN_S  # Reset backoff
                self._hedges_executed += 1
                entry["status"]   = "success"
                entry["tx_hash"]  = result.get("tx_hash", "unknown")

                log.info(
                    "auto_hedge_success",
                    symbol=self._symbol,
                    net_delta=round(net_delta, 6),
                    amount=round(amount, 6),
                    tx_hash=entry["tx_hash"],
                )

                await self._record_trade(
                    net_delta=net_delta,
                    amount=amount,
                    status="success",
                    detail=f"Lighter hedge tx={entry['tx_hash']}",
                    bybit_fill_price=bybit_entry_price,
                    lighter_fill_price=result.get("estimated_price"),
                    spread_bps_at_entry=spread_bps_at_entry,
                )

            except Exception as e:
                err_msg = str(e)

                # Sub-minimum amount — not an error, just skip silently
                if "below Lighter minimum" in err_msg:
                    log.debug("auto_hedge_below_min_skipped", amount=amount)
                    return

                # Real failure — apply exponential backoff
                self._last_failed_ts = time.time()
                self._cooldown_s     = min(MAX_COOLDOWN_S, self._cooldown_s * 2)

                entry["status"] = "error"
                entry["error"]  = err_msg
                log.error(
                    "auto_hedge_lighter_failed",
                    symbol=self._symbol,
                    net_delta=round(net_delta, 6),
                    error=err_msg,
                    next_retry_in=self._cooldown_s,
                )

                await self._record_trade(
                    net_delta=net_delta,
                    amount=amount,
                    status="failed",
                    detail=err_msg,
                    bybit_fill_price=bybit_entry_price,
                    lighter_fill_price=None,
                    spread_bps_at_entry=spread_bps_at_entry,
                )

            finally:
                self._hedge_log.append(entry)
                if len(self._hedge_log) > MAX_HEDGE_LOG:
                    self._hedge_log = self._hedge_log[-MAX_HEDGE_LOG:]

    # ─── Lifecycle ────────────────────────────────────────────────────────

    async def start(
        self,
        symbol: str = "XAUTUSDT",
        poll_interval_s: float = 2.0,
        min_delta: float = 0.001,
        **kwargs,
    ):
        if self._running:
            raise RuntimeError("Auto-hedge already running")

        self._symbol           = symbol
        self._poll_interval_s  = max(0.5, poll_interval_s)
        self._min_delta        = max(0.0001, min_delta)
        self._last_failed_ts   = 0.0
        self._last_hedge_ts    = 0.0
        self._cooldown_s       = INITIAL_COOLDOWN_S
        self._consecutive_errors = 0
        self._hedges_executed  = 0
        self._hedge_log        = []
        self._started_at       = time.time()

        self._bybit   = BybitClient(settings)
        self._lighter = LighterClient(settings)

        self._running = True
        self._task    = asyncio.create_task(self._supervised_loop())
        log.info(
            "auto_hedge_started",
            symbol=symbol,
            poll_interval_s=self._poll_interval_s,
            min_delta=self._min_delta,
            post_hedge_wait_s=POST_HEDGE_WAIT_S,
        )

    async def _supervised_loop(self):
        """Supervisor: restart poll_loop on unexpected crash."""
        while self._running:
            try:
                await self._poll_loop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("auto_hedge_crashed", error=str(e))
                if self._running:
                    await asyncio.sleep(2)
                    log.info("auto_hedge_restarting")

    async def stop(self):
        if not self._running:
            raise RuntimeError("Auto-hedge not running")

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._lighter:
            await self._lighter.close()
            self._lighter = None
        if self._bybit and hasattr(self._bybit, "close"):
            await self._bybit.close()
        self._bybit = None

        log.info("auto_hedge_stopped", symbol=self._symbol)

    async def recreate_clients(self):
        """Recreate Bybit/Lighter clients with current settings."""
        if not self._running:
            return
        old_lighter   = self._lighter
        self._bybit   = BybitClient(settings)
        self._lighter = LighterClient(settings)
        if old_lighter:
            await old_lighter.close()
        log.info("auto_hedge_clients_recreated", symbol=self._symbol)

    def status(self) -> dict:
        return {
            "running":            self._running,
            "symbol":             self._symbol,
            "source_exchange":    "bybit",
            "poll_interval_s":    self._poll_interval_s,
            "min_delta":          self._min_delta,
            "post_hedge_wait_s":  POST_HEDGE_WAIT_S,
            "last_failed_ts":     self._last_failed_ts,
            "cooldown_s":         self._cooldown_s,
            "last_hedge_ts":      self._last_hedge_ts,
            "hedges_executed":    self._hedges_executed,
            "consecutive_errors": self._consecutive_errors,
            "started_at":         self._started_at,
            "recent_hedges":      self._hedge_log[-20:],
        }

    # ─── Trade recording ──────────────────────────────────────────────────

    async def _record_trade(
        self,
        net_delta: float,
        amount: float,
        status: str,
        detail: str,
        bybit_fill_price: Optional[float] = None,
        lighter_fill_price: Optional[float] = None,
        spread_bps_at_entry: Optional[float] = None,
    ):
        is_ask  = net_delta > 0
        # PNL for auto_hedge is not meaningful (it's a rebalance, not arb)
        # so we store None to avoid misleading numbers in the journal
        trade = TradeRecord(
            ts=time.time() * 1000,
            symbol=self._symbol,
            strategy="auto_hedge",
            side="SELL_LIGHTER" if is_ask else "BUY_LIGHTER",
            qty_requested=amount,
            qty_filled=amount if status == "success" else 0.0,
            bybit_side="Buy" if net_delta > 0 else "Sell",
            bybit_fill_price=bybit_fill_price,
            lighter_fill_price=lighter_fill_price,
            spread_bps_at_entry=spread_bps_at_entry,
            net_pnl_usd=None,   # Rebalance — no arb PNL
            status=status,
            detail=detail,
        )
        await record_trade(trade)


# ─── Module-level singleton ────────────────────────────────────────────────

_instance: Optional[AutoHedgeService] = None


def get_auto_hedge_service() -> AutoHedgeService:
    global _instance
    if _instance is None:
        _instance = AutoHedgeService()
    return _instance
