"""Periodic position reconciliation between Bybit and Lighter."""
import asyncio
import time
from typing import Optional

import structlog

from app.alerts.alert_engine import send_system_alert
from app.collectors.bybit_client import BybitClient
from app.collectors.lighter_client import LighterClient
from app.config import settings

log = structlog.get_logger()


class ReconciliationService:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval_s = 30.0
        self.delta_threshold = 0.001
        self.last_check_ts: Optional[float] = None
        self.last_mismatches: list[dict] = []
        self.consecutive_errors = 0
        self._bybit: Optional[BybitClient] = None
        self._lighter: Optional[LighterClient] = None

    async def start(self):
        if self._running:
            return
        self._bybit = BybitClient(settings)
        self._lighter = LighterClient(settings)
        self._running = True
        self._task = asyncio.create_task(self._loop())
        log.info("reconciliation_started", interval_s=self.poll_interval_s)

    async def stop(self):
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
        self._bybit = None
        log.info("reconciliation_stopped")

    async def _loop(self):
        while self._running:
            try:
                await self._check_once()
                self.consecutive_errors = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.consecutive_errors += 1
                log.error("reconciliation_error", error=str(e), consecutive=self.consecutive_errors)
            await asyncio.sleep(self.poll_interval_s)

    async def _check_once(self):
        mismatches: list[dict] = []
        for symbol in settings.symbol_list:
            bybit_pos, lighter_pos = await asyncio.wait_for(
                asyncio.gather(
                    self._bybit.get_position(symbol),
                    self._lighter.get_position(symbol),
                ),
                timeout=20.0,
            )
            bybit_qty = self._signed_qty(bybit_pos)
            lighter_qty = self._signed_qty(lighter_pos)
            net_delta = bybit_qty + lighter_qty

            if abs(net_delta) > self.delta_threshold:
                mismatch = {
                    "symbol": symbol,
                    "bybit_qty": bybit_qty,
                    "lighter_qty": lighter_qty,
                    "net_delta": net_delta,
                    "threshold": self.delta_threshold,
                }
                mismatches.append(mismatch)
                await send_system_alert(
                    "position_mismatch",
                    (
                        f"Position mismatch {symbol}: "
                        f"bybit={bybit_qty:.6f}, lighter={lighter_qty:.6f}, "
                        f"net_delta={net_delta:.6f}"
                    ),
                    severity="critical",
                    value=abs(net_delta),
                    threshold=self.delta_threshold,
                )

        self.last_check_ts = time.time() * 1000
        self.last_mismatches = mismatches
        log.info("reconciliation_checked", mismatches=len(mismatches))

    def status(self) -> dict:
        return {
            "running": self._running,
            "poll_interval_s": self.poll_interval_s,
            "delta_threshold": self.delta_threshold,
            "last_check_ts": self.last_check_ts,
            "mismatches": self.last_mismatches,
            "consecutive_errors": self.consecutive_errors,
        }

    def _signed_qty(self, pos: dict) -> float:
        amount = float(pos.get("amount", 0.0) or 0.0)
        if amount == 0:
            return 0.0
        return amount if pos.get("is_long", True) else -amount


_instance: Optional[ReconciliationService] = None


def get_reconciliation_service() -> ReconciliationService:
    global _instance
    if _instance is None:
        _instance = ReconciliationService()
    return _instance
