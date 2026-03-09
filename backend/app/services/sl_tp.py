"""
SL/TP Service — monitors mark price deviation from entry and auto-closes.

Background asyncio task that:
1. Polls Bybit + Lighter positions every N seconds
2. Gets mark price and entry price
3. If mark_price >= entry + tp_delta → TP trigger
4. If mark_price <= entry - sl_delta → SL trigger
5. On trigger: closes all positions via executor + logs event
"""
import asyncio
import time
import structlog
from typing import Optional

from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.services.executor import ArbitrageExecutor
from app.config import settings

log = structlog.get_logger()

MAX_TRIGGER_LOG = 50


class SlTpService:
    def __init__(self):
        self._running: bool = False
        self._task: Optional[asyncio.Task] = None
        self._symbol: str = ""
        self._sl_delta: float = 0.0  # price drop from entry to trigger SL
        self._tp_delta: float = 0.0  # price rise from entry to trigger TP
        self._poll_interval_s: float = 2.0
        self._last_mark_price: Optional[float] = None
        self._entry_price: Optional[float] = None
        self._triggered: bool = False
        self._trigger_type: Optional[str] = None  # "SL" or "TP"
        self._trigger_log: list[dict] = []
        self._consecutive_errors: int = 0
        self._started_at: Optional[float] = None
        self._bybit: Optional[BybitClient] = None
        self._lighter: Optional[LighterClient] = None

    async def _poll_loop(self):
        while self._running:
            try:
                bybit_pos, lighter_pos = await asyncio.wait_for(
                    asyncio.gather(
                        self._bybit.get_position(self._symbol),
                        self._lighter.get_position(self._symbol),
                    ),
                    timeout=15.0,
                )

                self._consecutive_errors = 0

                has_position = (
                    bybit_pos.get("amount", 0) > 0
                    or lighter_pos.get("amount", 0) > 0
                )

                if not has_position:
                    await asyncio.sleep(self._poll_interval_s)
                    continue

                # Get mark price (prefer Bybit, fallback Lighter)
                mark = bybit_pos.get("mark_price", 0) or lighter_pos.get("mark_price", 0)
                if not mark:
                    await asyncio.sleep(self._poll_interval_s)
                    continue

                self._last_mark_price = mark

                # Get entry price (average of both exchanges if both have positions)
                b_entry = bybit_pos.get("entry_price", 0) if bybit_pos.get("amount", 0) > 0 else 0
                l_entry = lighter_pos.get("entry_price", 0) if lighter_pos.get("amount", 0) > 0 else 0

                if b_entry > 0 and l_entry > 0:
                    entry = (b_entry + l_entry) / 2
                elif b_entry > 0:
                    entry = b_entry
                elif l_entry > 0:
                    entry = l_entry
                else:
                    await asyncio.sleep(self._poll_interval_s)
                    continue

                self._entry_price = entry

                # Check SL: mark price drops below entry - sl_delta
                if self._sl_delta > 0 and mark <= entry - self._sl_delta:
                    await self._trigger("SL", mark, entry)
                    return

                # Check TP: mark price rises above entry + tp_delta
                if self._tp_delta > 0 and mark >= entry + self._tp_delta:
                    await self._trigger("TP", mark, entry)
                    return

            except asyncio.CancelledError:
                raise
            except Exception as e:
                self._consecutive_errors += 1
                log.error("sl_tp_poll_error",
                          error=str(e),
                          consecutive=self._consecutive_errors)

            await asyncio.sleep(self._poll_interval_s)

    async def _trigger(self, trigger_type: str, mark_price: float, entry_price: float):
        """Execute SL or TP: close all positions."""
        self._triggered = True
        self._trigger_type = trigger_type

        deviation = mark_price - entry_price

        log.info("sl_tp_triggered",
                 type=trigger_type,
                 symbol=self._symbol,
                 mark_price=round(mark_price, 2),
                 entry_price=round(entry_price, 2),
                 deviation=round(deviation, 2))

        entry = {
            "ts": time.time(),
            "type": trigger_type,
            "symbol": self._symbol,
            "mark_price": round(mark_price, 2),
            "entry_price": round(entry_price, 2),
            "deviation": round(deviation, 2),
            "status": "pending",
        }

        try:
            executor = ArbitrageExecutor(settings)
            result = await executor.emergency_close_auto(self._symbol)
            entry["status"] = result.get("status", "unknown")
            entry["detail"] = result.get("detail", "")
            log.info("sl_tp_close_result",
                     type=trigger_type,
                     status=entry["status"],
                     detail=entry["detail"])
        except Exception as e:
            entry["status"] = "error"
            entry["error"] = str(e)
            log.error("sl_tp_close_failed",
                      type=trigger_type,
                      error=str(e))

        self._trigger_log.append(entry)
        if len(self._trigger_log) > MAX_TRIGGER_LOG:
            self._trigger_log = self._trigger_log[-MAX_TRIGGER_LOG:]

        # Auto-stop after trigger
        self._running = False

    async def start(self, symbol: str = "BTCUSDT",
                    sl_delta: float = 0.0,
                    tp_delta: float = 0.0,
                    poll_interval_s: float = 2.0,
                    **kwargs):
        if self._running:
            raise RuntimeError("SL/TP already running")

        if sl_delta <= 0 and tp_delta <= 0:
            raise ValueError("At least one of sl_delta or tp_delta must be > 0")

        self._symbol = symbol
        self._sl_delta = sl_delta
        self._tp_delta = tp_delta
        self._poll_interval_s = max(0.5, poll_interval_s)
        self._last_mark_price = None
        self._entry_price = None
        self._triggered = False
        self._trigger_type = None
        self._consecutive_errors = 0
        self._started_at = time.time()

        self._bybit = BybitClient(settings)
        self._lighter = LighterClient(settings)

        self._running = True
        self._task = asyncio.create_task(self._supervised_loop())
        log.info("sl_tp_started",
                 symbol=symbol,
                 sl_delta=sl_delta,
                 tp_delta=tp_delta,
                 poll_interval_s=self._poll_interval_s)

    async def _supervised_loop(self):
        """Supervisor: restart poll_loop on crash."""
        while self._running:
            try:
                await self._poll_loop()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error("sl_tp_crashed", error=str(e))
                if self._running:
                    await asyncio.sleep(2)
                    log.info("sl_tp_restarting")

    async def stop(self):
        if not self._running:
            raise RuntimeError("SL/TP not running")

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

        log.info("sl_tp_stopped", symbol=self._symbol)

    def reset(self):
        """Clear triggered state so the UI is no longer stuck."""
        self._triggered = False
        self._trigger_type = None
        log.info("sl_tp_reset", symbol=self._symbol)

    def status(self) -> dict:
        return {
            "running": self._running,
            "symbol": self._symbol,
            "sl_delta": self._sl_delta,
            "tp_delta": self._tp_delta,
            "poll_interval_s": self._poll_interval_s,
            "last_mark_price": self._last_mark_price,
            "entry_price": self._entry_price,
            "triggered": self._triggered,
            "trigger_type": self._trigger_type,
            "consecutive_errors": self._consecutive_errors,
            "started_at": self._started_at,
            "recent_triggers": self._trigger_log[-20:],
        }


# Module-level singleton
_instance: Optional[SlTpService] = None


def get_sl_tp_service() -> SlTpService:
    global _instance
    if _instance is None:
        _instance = SlTpService()
    return _instance
