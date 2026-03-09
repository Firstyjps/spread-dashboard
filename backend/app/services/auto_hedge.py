"""
Auto-Hedge Service — monitors Bybit position changes and hedges on Lighter.

Background asyncio task that:
1. Polls Bybit position for a configured symbol every N seconds
2. Tracks previous position (size + direction as a signed quantity)
3. When delta != 0, places an IOC market order on Lighter in the opposite direction
"""
import asyncio
import time
import structlog
from typing import Optional

from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.config import settings

log = structlog.get_logger()

MAX_HEDGE_LOG = 100


class AutoHedgeService:
    def __init__(self):
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._symbol: str = ""
        self._poll_interval_s: float = 2.0
        self._min_delta: float = 0.001
        self._last_signed_pos: Optional[float] = None
        self._hedge_log: list[dict] = []
        self._consecutive_errors: int = 0
        self._hedges_executed: int = 0
        self._bybit: Optional[BybitClient] = None
        self._lighter: Optional[LighterClient] = None
        self._lock = asyncio.Lock()
        self._started_at: Optional[float] = None

    def _to_signed(self, pos: dict) -> float:
        """Convert Bybit position dict to signed float (+long, -short)."""
        amount = pos.get("amount", 0.0)
        if amount == 0:
            return 0.0
        return amount if pos.get("is_long", True) else -amount

    async def _poll_loop(self):
        while self._running:
            try:
                pos = await self._bybit.get_position(self._symbol)
                current = self._to_signed(pos)

                # First poll: record baseline, don't hedge
                if self._last_signed_pos is None:
                    self._last_signed_pos = current
                    log.info("auto_hedge_baseline",
                             symbol=self._symbol,
                             position=current)
                    await asyncio.sleep(self._poll_interval_s)
                    continue

                # Guard: if previous position was non-zero and now suddenly zero,
                # could be API error (bybit returns 0 on timeout/error).
                # Skip this cycle — wait for confirmation next poll.
                if self._last_signed_pos != 0.0 and current == 0.0:
                    # Check if this is a real close or API error by polling again
                    await asyncio.sleep(0.5)
                    confirm_pos = await self._bybit.get_position(self._symbol)
                    confirm = self._to_signed(confirm_pos)
                    if confirm != 0.0:
                        # Was API error, skip
                        log.warning("auto_hedge_false_zero_skipped",
                                    symbol=self._symbol)
                        self._consecutive_errors += 1
                        await asyncio.sleep(self._poll_interval_s)
                        continue
                    # Confirmed zero — position truly closed
                    current = 0.0

                delta = current - self._last_signed_pos
                self._consecutive_errors = 0

                if abs(delta) >= self._min_delta:
                    await self._execute_hedge(delta, current)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_errors += 1
                log.error("auto_hedge_poll_error",
                          error=str(e),
                          consecutive=self._consecutive_errors)

            await asyncio.sleep(self._poll_interval_s)

    async def _execute_hedge(self, delta: float, current_pos: float):
        """Place hedge order on Lighter for the detected delta."""
        async with self._lock:
            # Bybit long (delta > 0) → sell on Lighter (is_ask=True)
            # Bybit short (delta < 0) → buy on Lighter (is_ask=False)
            is_ask = delta > 0
            amount = abs(delta)
            side_str = "SELL" if is_ask else "BUY"

            log.info("auto_hedge_executing",
                     symbol=self._symbol,
                     delta=round(delta, 6),
                     lighter_side=side_str,
                     amount=amount)

            entry = {
                "ts": time.time(),
                "symbol": self._symbol,
                "delta": round(delta, 6),
                "lighter_side": side_str,
                "amount": amount,
                "status": "pending",
            }

            try:
                result = await self._lighter.place_market_order(
                    symbol=self._symbol,
                    amount=amount,
                    is_ask=is_ask,
                )
                # Success — update last position
                self._last_signed_pos = current_pos
                self._hedges_executed += 1
                entry["status"] = "success"
                entry["tx_hash"] = result.get("tx_hash", "unknown")
                log.info("auto_hedge_success",
                         symbol=self._symbol,
                         delta=round(delta, 6),
                         tx_hash=entry["tx_hash"])

            except Exception as e:
                # Don't update last_signed_pos — will retry next cycle
                entry["status"] = "error"
                entry["error"] = str(e)
                log.error("auto_hedge_lighter_failed",
                          symbol=self._symbol,
                          delta=round(delta, 6),
                          error=str(e))

            self._hedge_log.append(entry)
            if len(self._hedge_log) > MAX_HEDGE_LOG:
                self._hedge_log = self._hedge_log[-MAX_HEDGE_LOG:]

    async def start(self, symbol: str = "BTCUSDT",
                    poll_interval_s: float = 2.0,
                    min_delta: float = 0.001,
                    **kwargs):
        if self._running:
            raise RuntimeError("Auto-hedge already running")

        self._symbol = symbol
        self._poll_interval_s = max(0.5, poll_interval_s)
        self._min_delta = max(0.0001, min_delta)
        self._last_signed_pos = None
        self._consecutive_errors = 0
        self._hedges_executed = 0
        self._hedge_log = []
        self._started_at = time.time()

        self._bybit = BybitClient(settings)
        self._lighter = LighterClient(settings)

        self._running = True
        self._task = asyncio.create_task(self._supervised_loop())
        log.info("auto_hedge_started",
                 symbol=symbol,
                 poll_interval_s=self._poll_interval_s,
                 min_delta=self._min_delta)

    async def _supervised_loop(self):
        """Supervisor: restart poll_loop on crash."""
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
        if self._bybit and hasattr(self._bybit, 'close'):
            await self._bybit.close()
        self._bybit = None

        log.info("auto_hedge_stopped", symbol=self._symbol)

    def status(self) -> dict:
        return {
            "running": self._running,
            "symbol": self._symbol,
            "source_exchange": "bybit",
            "poll_interval_s": self._poll_interval_s,
            "min_delta": self._min_delta,
            "last_signed_position": self._last_signed_pos,
            "hedges_executed": self._hedges_executed,
            "consecutive_errors": self._consecutive_errors,
            "started_at": self._started_at,
            "recent_hedges": self._hedge_log[-20:],
        }


# Module-level singleton
_instance: Optional[AutoHedgeService] = None


def get_auto_hedge_service() -> AutoHedgeService:
    global _instance
    if _instance is None:
        _instance = AutoHedgeService()
    return _instance
