# file: backend/app/alerts/telegram_bot.py
"""
Telegram Bot command handler with long-polling.
Receives commands from Telegram and responds interactively.

Commands:
  /status              - Current spread & prices for all symbols
  /threshold           - Show current alert thresholds
  /set SYMBOL UP LOW   - Change thresholds at runtime
  /mute [minutes]      - Mute alerts (default 30 min)
  /unmute              - Resume alerts
  /history [SYMBOL]    - Last 10 alerts from DB
  /ping                - Health check
  /help                - Show available commands
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
import structlog

from app.config import settings

log = structlog.get_logger()

_TELEGRAM_API = "https://api.telegram.org"
_TZ_BANGKOK = ZoneInfo("Asia/Bangkok")
_POLL_TIMEOUT = 30  # long-poll timeout seconds

# --- Mute state ---
_muted_until: float = 0.0  # monotonic timestamp


def is_muted() -> bool:
    """Check if alerts are currently muted."""
    return time.monotonic() < _muted_until


def mute_for(minutes: float) -> None:
    """Mute alerts for N minutes."""
    global _muted_until
    _muted_until = time.monotonic() + minutes * 60


def unmute() -> None:
    """Unmute alerts immediately."""
    global _muted_until
    _muted_until = 0.0


# --- Runtime threshold overrides ---
# Key: symbol, Value: (upper_bps, lower_bps)
_runtime_overrides: dict[str, tuple[float, float]] = {}


def get_runtime_threshold(symbol: str) -> Optional[tuple[float, float]]:
    """Get runtime threshold override for a symbol, or None."""
    return _runtime_overrides.get(symbol)


# --- Command handlers ---

async def _cmd_ping(chat_id: str, _args: str, session: aiohttp.ClientSession) -> str:
    return "\U0001f3d3 pong — bot is alive"


async def _cmd_help(chat_id: str, _args: str, session: aiohttp.ClientSession) -> str:
    return (
        "<b>Available commands:</b>\n"
        "/status — Current spread & prices\n"
        "/threshold — Show alert thresholds\n"
        "/set SYMBOL UPPER LOWER — Change threshold\n"
        "/mute [minutes] — Mute alerts (default 30)\n"
        "/unmute — Resume alerts\n"
        "/history [SYMBOL] — Last 10 alerts\n"
        "/ping — Health check"
    )


async def _cmd_status(chat_id: str, _args: str, session: aiohttp.ClientSession) -> str:
    # Import here to avoid circular imports
    from app.analytics.spread_engine import get_all_current_data
    data = get_all_current_data()
    if not data:
        return "\u26a0\ufe0f No data available yet."

    lines = ["<b>\U0001f4ca Spread Status</b>\n"]
    for symbol, info in data.items():
        spread = info.get("spread")
        if not spread:
            lines.append(f"<b>{symbol}</b>: no spread data")
            continue

        long_bps = abs(spread["long_spread"]) * 10_000
        short_bps = abs(spread["short_spread"]) * 10_000
        metric_bps = max(long_bps, short_bps)
        bybit_mid = (spread["bybit_bid"] + spread["bybit_ask"]) / 2
        lighter_mid = (spread["lighter_bid"] + spread["lighter_ask"]) / 2

        lines.append(
            f"<b>{symbol}</b>\n"
            f"  metric={metric_bps:.2f} bps\n"
            f"  bybit mid={bybit_mid:.2f}\n"
            f"  lighter mid={lighter_mid:.2f}"
        )

    # Mute status
    if is_muted():
        remaining = (_muted_until - time.monotonic()) / 60
        lines.append(f"\n\U0001f507 Muted for {remaining:.0f} more minutes")

    now_bkk = datetime.now(timezone.utc).astimezone(_TZ_BANGKOK)
    lines.append(f"\n{now_bkk.strftime('%d-%b-%y %H:%M')} GMT+7")
    return "\n".join(lines)


async def _cmd_threshold(chat_id: str, _args: str, session: aiohttp.ClientSession) -> str:
    lines = ["<b>\U0001f4cf Alert Thresholds</b>\n"]
    lines.append(
        f"Global: upper={settings.alert_upper_bps} bps, "
        f"lower={settings.alert_lower_bps} bps\n"
    )

    # .env overrides
    if settings.alert_overrides:
        lines.append("<b>Per-symbol (.env):</b>")
        for entry in settings.alert_overrides.split(","):
            entry = entry.strip()
            if entry:
                lines.append(f"  {entry.replace(':', ' → upper=', 1).replace(':', ' lower=', 1)}")

    # Runtime overrides
    if _runtime_overrides:
        lines.append("\n<b>Runtime overrides (/set):</b>")
        for sym, (up, lo) in _runtime_overrides.items():
            lines.append(f"  {sym}: upper={up} bps, lower={lo} bps")

    return "\n".join(lines)


async def _cmd_set(chat_id: str, args: str, session: aiohttp.ClientSession) -> str:
    parts = args.strip().split()
    if len(parts) != 3:
        return "\u26a0\ufe0f Usage: /set SYMBOL UPPER LOWER\nExample: /set XAUTUSDT 82 70"
    symbol, upper_s, lower_s = parts
    try:
        upper = float(upper_s)
        lower = float(lower_s)
    except ValueError:
        return "\u26a0\ufe0f UPPER and LOWER must be numbers."
    if upper <= lower:
        return "\u26a0\ufe0f UPPER must be greater than LOWER."

    _runtime_overrides[symbol.upper()] = (upper, lower)
    return f"\u2705 Threshold updated: <b>{symbol.upper()}</b>\nupper={upper} bps, lower={lower} bps"


async def _cmd_mute(chat_id: str, args: str, session: aiohttp.ClientSession) -> str:
    minutes = 30.0
    if args.strip():
        try:
            minutes = float(args.strip())
        except ValueError:
            return "\u26a0\ufe0f Usage: /mute [minutes]\nExample: /mute 60"
    if minutes <= 0:
        return "\u26a0\ufe0f Minutes must be positive."

    mute_for(minutes)
    return f"\U0001f507 Alerts muted for <b>{minutes:.0f} minutes</b>"


async def _cmd_unmute(chat_id: str, _args: str, session: aiohttp.ClientSession) -> str:
    unmute()
    return "\U0001f50a Alerts unmuted — notifications resumed"


async def _cmd_history(chat_id: str, args: str, session: aiohttp.ClientSession) -> str:
    from app.storage.database import get_recent_alerts
    symbol = args.strip().upper() if args.strip() else None
    alerts = await get_recent_alerts(limit=50)

    if symbol:
        alerts = [a for a in alerts if a.get("symbol") == symbol]

    alerts = alerts[:10]
    if not alerts:
        msg = f"No recent alerts"
        if symbol:
            msg += f" for {symbol}"
        return msg

    lines = [f"<b>\U0001f4dc Alert History</b>"]
    if symbol:
        lines[0] += f" ({symbol})"
    lines.append("")

    for a in alerts:
        ts = datetime.fromtimestamp(a["ts"] / 1000, tz=timezone.utc).astimezone(_TZ_BANGKOK)
        ts_str = ts.strftime("%d-%b %H:%M")
        alert_type = a.get("alert_type", "")
        emoji = "\U0001f6a8" if "alert" in alert_type else "\u2705"
        value = a.get("value", 0)
        lines.append(f"{emoji} {ts_str} | {a.get('symbol','')} | {value:.1f} bps")

    return "\n".join(lines)


# --- Command dispatcher ---

_COMMANDS = {
    "/ping": _cmd_ping,
    "/help": _cmd_help,
    "/start": _cmd_help,
    "/status": _cmd_status,
    "/threshold": _cmd_threshold,
    "/set": _cmd_set,
    "/mute": _cmd_mute,
    "/unmute": _cmd_unmute,
    "/history": _cmd_history,
}


async def _handle_message(message: dict, session: aiohttp.ClientSession) -> None:
    """Parse and handle a single Telegram message."""
    text = message.get("text", "").strip()
    chat_id = str(message.get("chat", {}).get("id", ""))

    if not text or not chat_id:
        return

    # Only respond to the configured chat
    if chat_id != settings.telegram_chat_id:
        log.debug("telegram_bot_ignoring_chat", chat_id=chat_id)
        return

    # Parse command and args
    if not text.startswith("/"):
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]  # strip @botname suffix
    args = parts[1] if len(parts) > 1 else ""

    handler = _COMMANDS.get(cmd)
    if not handler:
        return  # ignore unknown commands silently

    try:
        response = await handler(chat_id, args, session)
        await _send_reply(chat_id, response, session)
    except Exception as e:
        log.error("telegram_bot_handler_error", cmd=cmd, error=str(e))
        await _send_reply(chat_id, f"\u274c Error: {e}", session)


async def _send_reply(chat_id: str, text: str, session: aiohttp.ClientSession) -> None:
    """Send a reply message."""
    url = f"{_TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                log.warning("telegram_bot_reply_error", status=resp.status, body=body[:200])
    except Exception as e:
        log.warning("telegram_bot_reply_failed", error=str(e))


# --- Polling loop ---

async def start_polling() -> None:
    """Long-poll Telegram getUpdates and dispatch commands. Runs forever."""
    if not settings.telegram_enabled or not settings.telegram_bot_token:
        log.info("telegram_bot_disabled")
        return

    log.info("telegram_bot_starting")
    offset = 0
    url = f"{_TELEGRAM_API}/bot{settings.telegram_bot_token}/getUpdates"

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=_POLL_TIMEOUT + 10),
        connector=aiohttp.TCPConnector(limit=3),
    ) as session:
        while True:
            try:
                params = {
                    "offset": offset,
                    "timeout": _POLL_TIMEOUT,
                    "allowed_updates": '["message"]',
                }
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        log.warning("telegram_poll_error", status=resp.status)
                        await asyncio.sleep(5)
                        continue
                    data = await resp.json()

                if not data.get("ok"):
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    message = update.get("message")
                    if message:
                        await _handle_message(message, session)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("telegram_poll_exception", error=str(e))
                await asyncio.sleep(5)
