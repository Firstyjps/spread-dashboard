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
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo

import structlog

from app.config import settings
from app.models import SpreadMetric, Alert
from app.storage.database import insert_alert, commit as db_commit
from app.alerts.telegram_notifier import send_telegram

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Timezone constant
# ---------------------------------------------------------------------------
_TZ_BANGKOK = ZoneInfo("Asia/Bangkok")


# ---------------------------------------------------------------------------
# Pure helper functions (side logic, formatting)
# ---------------------------------------------------------------------------

def decide_side(spread_bps: float, upper: float, lower: float) -> Optional[str]:
    """
    Determine the trading side from threshold breach.

    Upper breach (spread too wide)   -> SHORT the spread
    Lower breach (spread too narrow) -> LONG  the spread
    Dead zone                        -> None  (no alert)
    """
    if spread_bps >= upper:
        return "SHORT"
    if spread_bps <= lower:
        return "LONG"
    return None


def _safe_mid(bid: float | None, ask: float | None) -> str:
    """Compute mid-price formatted to 2 decimal places, or 'N/A' if inputs missing."""
    if bid is None or ask is None:
        return "N/A"
    return f"{(bid + ask) / 2:.2f}"


def _format_ts_bangkok(ts_utc: datetime) -> str:
    """Convert UTC datetime to Asia/Bangkok and format as DD-Mon-YY HH:MM GMT+7."""
    bkk = ts_utc.astimezone(_TZ_BANGKOK)
    return bkk.strftime("%d-%b-%y %H:%M") + " GMT+7"


def build_alert_message(
    symbol: str,
    spread_bps: float,
    upper_bps: float,
    lower_bps: float,
    side: str,
    bybit_bid: float | None,
    bybit_ask: float | None,
    lighter_bid: float | None,
    lighter_ask: float | None,
    ts_utc: datetime,
) -> str:
    """
    Build the Telegram alert message.  Single source of truth for formatting.
    Handles mid-price calculation, 2-decimal formatting, and timezone conversion.
    """
    return (
        f"\U0001f6a8 <b>SPREAD ALERT {symbol}</b>\n"
        f"metric={spread_bps:.2f} bps (upper={upper_bps:.2f})\n"
        f"Side={side}\n"
        f"bybit mid={_safe_mid(bybit_bid, bybit_ask)}\n"
        f"lighter mid={_safe_mid(lighter_bid, lighter_ask)}\n"
        f"{_format_ts_bangkok(ts_utc)}"
    )


def build_recovery_message(
    symbol: str,
    spread_bps: float,
    lower_bps: float,
    bybit_bid: float | None,
    bybit_ask: float | None,
    lighter_bid: float | None,
    lighter_ask: float | None,
    ts_utc: datetime,
) -> str:
    """Build the Telegram recovery message with identical formatting standards."""
    return (
        f"\u2705 <b>SPREAD NORMAL {symbol}</b>\n"
        f"metric={spread_bps:.2f} bps (lower={lower_bps:.2f})\n"
        f"bybit mid={_safe_mid(bybit_bid, bybit_ask)}\n"
        f"lighter mid={_safe_mid(lighter_bid, lighter_ask)}\n"
        f"{_format_ts_bangkok(ts_utc)}"
    )


# ---------------------------------------------------------------------------
# State machine internals
# ---------------------------------------------------------------------------

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
    Returns (metric_bps, dominant_leg) where dominant_leg is "LONG" or "SHORT".
    Uses max(abs(long_spread), abs(short_spread)) * 10000.

    NOTE: dominant_leg indicates which spread leg is larger — it is NOT the
    trading side for the alert.  Use decide_side() for the alert side.
    """
    long_bps = abs(spread.long_spread) * 10_000
    short_bps = abs(spread.short_spread) * 10_000
    if long_bps >= short_bps:
        return long_bps, "LONG"
    return short_bps, "SHORT"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def on_spread_update(spread: SpreadMetric) -> None:
    """
    Main entry point. Called for every spread computation in poll_loop.
    Evaluates state transitions, fires Telegram + DB alerts via fire-and-forget tasks.
    """
    if not settings.telegram_enabled:
        return

    symbol = spread.symbol
    state = _get_state(symbol)
    metric_bps, _dominant_leg = _compute_metric_bps(spread)
    now = time.monotonic()
    cooldown = settings.telegram_alert_cooldown_s
    ts_utc = datetime.fromtimestamp(spread.ts / 1000, tz=timezone.utc)

    # Per-symbol thresholds (falls back to global defaults)
    upper_bps, lower_bps = settings.get_alert_thresholds(symbol)

    if state.state == AlertState.NORMAL:
        if metric_bps >= upper_bps:
            # NORMAL -> ALERTING
            state.state = AlertState.ALERTING
            state.last_metric_bps = metric_bps
            side = decide_side(
                metric_bps, upper_bps, lower_bps,
            ) or "SHORT"  # guaranteed non-None here, defensive fallback
            state.last_side = side
            log.warning(
                "spread_alert_triggered",
                symbol=symbol,
                metric_bps=round(metric_bps, 2),
                side=side,
            )
            if now - state.last_notified_ts >= cooldown:
                state.last_notified_ts = now
                msg = build_alert_message(
                    symbol=symbol,
                    spread_bps=metric_bps,
                    upper_bps=upper_bps,
                    lower_bps=lower_bps,
                    side=side,
                    bybit_bid=spread.bybit_bid,
                    bybit_ask=spread.bybit_ask,
                    lighter_bid=spread.lighter_bid,
                    lighter_ask=spread.lighter_ask,
                    ts_utc=ts_utc,
                )
                asyncio.create_task(_send_and_store(
                    msg, spread, metric_bps,
                    alert_type="spread_alert",
                    severity="critical",
                    threshold=upper_bps,
                ))

    elif state.state == AlertState.ALERTING:
        if metric_bps <= lower_bps:
            # ALERTING -> NORMAL
            state.state = AlertState.NORMAL
            state.last_metric_bps = metric_bps
            log.info(
                "spread_alert_recovered",
                symbol=symbol,
                metric_bps=round(metric_bps, 2),
            )
            if now - state.last_notified_ts >= cooldown:
                state.last_notified_ts = now
                msg = build_recovery_message(
                    symbol=symbol,
                    spread_bps=metric_bps,
                    lower_bps=lower_bps,
                    bybit_bid=spread.bybit_bid,
                    bybit_ask=spread.bybit_ask,
                    lighter_bid=spread.lighter_bid,
                    lighter_ask=spread.lighter_ask,
                    ts_utc=ts_utc,
                )
                asyncio.create_task(_send_and_store(
                    msg, spread, metric_bps,
                    alert_type="spread_recovery",
                    severity="info",
                    threshold=lower_bps,
                ))


async def _send_and_store(
    message: str,
    spread: SpreadMetric,
    metric_bps: float,
    alert_type: str,
    severity: str,
    threshold: float = 0.0,
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
            threshold=threshold,
        )
        await insert_alert(alert)
        await db_commit()
    except Exception as e:
        log.error("alert_db_insert_error", error=str(e))


def reset_states() -> None:
    """Reset all per-symbol state. Useful for testing."""
    _states.clear()
