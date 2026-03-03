# file: backend/app/alerts/alert_engine.py
"""
Spread alert state machine.
Per-symbol states: NORMAL <-> ALERTING with hysteresis and cooldown.

Rules:
  NORMAL -> ALERTING  when metric_bps >= alert_upper_bps (default 60)
  ALERTING -> NORMAL  when metric_bps <= alert_lower_bps (default 30)
  Dead zone (30-60): no state change — prevents flapping.

Cooldown: skip Telegram send if within telegram_alert_cooldown_s of last send.
State always transitions immediately (reflects truth); only notification is suppressed.
"""
import asyncio
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Tuple

import structlog

from app.config import settings
from app.models import SpreadMetric, Alert
from app.storage.database import insert_alert
from app.alerts.telegram_notifier import send_telegram

log = structlog.get_logger()


class AlertState(Enum):
    NORMAL = "NORMAL"
    ALERTING = "ALERTING"


class SymbolAlertState:
    """Tracks state machine for one symbol."""
    __slots__ = ("state", "last_notified_ts", "last_metric_bps", "last_side")

    def __init__(self) -> None:
        self.state: AlertState = AlertState.NORMAL
        self.last_notified_ts: float = 0.0       # monotonic seconds
        self.last_metric_bps: float = 0.0
        self.last_side: str = ""


# Per-symbol state (module-level singleton)
_states: Dict[str, SymbolAlertState] = {}


def _get_state(symbol: str) -> SymbolAlertState:
    if symbol not in _states:
        _states[symbol] = SymbolAlertState()
    return _states[symbol]


def _compute_metric_bps(spread: SpreadMetric) -> Tuple[float, str]:
    """
    Compute the alert metric in basis points.
    Returns (metric_bps, side) where side is "LONG" or "SHORT".
    Uses max(abs(long_spread), abs(short_spread)) * 10000.
    """
    long_bps = abs(spread.long_spread) * 10_000
    short_bps = abs(spread.short_spread) * 10_000
    if long_bps >= short_bps:
        return long_bps, "LONG"
    return short_bps, "SHORT"


def _format_alert_message(
    spread: SpreadMetric, metric_bps: float, side: str,
) -> str:
    ts_iso = datetime.fromtimestamp(
        spread.ts / 1000, tz=timezone.utc,
    ).isoformat(timespec="seconds")
    return (
        f"\U0001f6a8 <b>SPREAD ALERT {spread.symbol}</b>\n"
        f"metric={metric_bps:.1f} bps (upper={settings.alert_upper_bps})\n"
        f"side={side}\n"
        f"bybit bid/ask={spread.bybit_bid}/{spread.bybit_ask}\n"
        f"lighter bid/ask={spread.lighter_bid}/{spread.lighter_ask}\n"
        f"ts={ts_iso}"
    )


def _format_recovery_message(
    spread: SpreadMetric, metric_bps: float,
) -> str:
    ts_iso = datetime.fromtimestamp(
        spread.ts / 1000, tz=timezone.utc,
    ).isoformat(timespec="seconds")
    return (
        f"\u2705 <b>SPREAD NORMAL {spread.symbol}</b>\n"
        f"metric={metric_bps:.1f} bps (lower={settings.alert_lower_bps})\n"
        f"ts={ts_iso}"
    )


async def on_spread_update(spread: SpreadMetric) -> None:
    """
    Main entry point. Called for every spread computation in poll_loop.
    Evaluates state transitions, fires Telegram + DB alerts via fire-and-forget tasks.
    """
    if not settings.telegram_enabled:
        return

    symbol = spread.symbol
    state = _get_state(symbol)
    metric_bps, side = _compute_metric_bps(spread)
    now = time.monotonic()
    cooldown = settings.telegram_alert_cooldown_s

    if state.state == AlertState.NORMAL:
        if metric_bps >= settings.alert_upper_bps:
            # NORMAL -> ALERTING
            state.state = AlertState.ALERTING
            state.last_metric_bps = metric_bps
            state.last_side = side
            log.warning(
                "spread_alert_triggered",
                symbol=symbol,
                metric_bps=round(metric_bps, 1),
                side=side,
            )
            if now - state.last_notified_ts >= cooldown:
                state.last_notified_ts = now
                msg = _format_alert_message(spread, metric_bps, side)
                asyncio.create_task(_send_and_store(
                    msg, spread, metric_bps,
                    alert_type="spread_alert",
                    severity="critical",
                ))

    elif state.state == AlertState.ALERTING:
        if metric_bps <= settings.alert_lower_bps:
            # ALERTING -> NORMAL
            state.state = AlertState.NORMAL
            state.last_metric_bps = metric_bps
            log.info(
                "spread_alert_recovered",
                symbol=symbol,
                metric_bps=round(metric_bps, 1),
            )
            if now - state.last_notified_ts >= cooldown:
                state.last_notified_ts = now
                msg = _format_recovery_message(spread, metric_bps)
                asyncio.create_task(_send_and_store(
                    msg, spread, metric_bps,
                    alert_type="spread_recovery",
                    severity="info",
                ))


async def _send_and_store(
    message: str,
    spread: SpreadMetric,
    metric_bps: float,
    alert_type: str,
    severity: str,
) -> None:
    """Fire-and-forget coroutine: send Telegram + insert DB alert."""
    try:
        await send_telegram(message)
    except Exception as e:
        log.error("telegram_task_error", error=str(e))

    try:
        alert = Alert(
            ts=spread.ts,
            alert_type=alert_type,
            symbol=spread.symbol,
            severity=severity,
            message=message,
            value=metric_bps,
            threshold=(
                settings.alert_upper_bps
                if alert_type == "spread_alert"
                else settings.alert_lower_bps
            ),
        )
        await insert_alert(alert)
    except Exception as e:
        log.error("alert_db_insert_error", error=str(e))


def reset_states() -> None:
    """Reset all per-symbol state. Useful for testing."""
    _states.clear()
