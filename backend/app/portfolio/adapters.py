"""
Exchange adapters — normalize raw exchange data into portfolio models.

Each adapter implements:
    name: str
    async fetch_balances() -> list[NormalizedBalance]
    async fetch_positions() -> list[NormalizedPosition]

Uses the existing BybitClient / LighterClient under the hood.
"""
from __future__ import annotations

import asyncio
import time
import structlog
from typing import Protocol, runtime_checkable

from pybit.unified_trading import HTTP

from app.portfolio.models import NormalizedBalance, NormalizedPosition
from app.utils.async_helpers import thread_with_timeout

log = structlog.get_logger()

# Timeout for individual exchange calls (seconds)
_ADAPTER_TIMEOUT = 12.0
# Retry config
_MAX_RETRIES = 2
_RETRY_DELAY = 0.5


# ─── Protocol ────────────────────────────────────────────────────

@runtime_checkable
class ExchangeAdapter(Protocol):
    name: str

    async def fetch_balances(self) -> list[NormalizedBalance]: ...
    async def fetch_positions(self) -> list[NormalizedPosition]: ...


# ─── Retry helper ────────────────────────────────────────────────

async def _retry(coro_fn, *args, retries: int = _MAX_RETRIES, **kwargs):
    """Retry a coroutine on transient errors (timeout / network)."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except (asyncio.TimeoutError, OSError, ConnectionError) as e:
            last_err = e
            if attempt < retries:
                log.warning("adapter_retry", attempt=attempt, error=str(e))
                await asyncio.sleep(_RETRY_DELAY * attempt)
        except Exception:
            raise  # non-transient → don't retry
    raise last_err  # type: ignore[misc]


# ─── Bybit Linear Adapter ───────────────────────────────────────

class BybitLinearAdapter:
    """Fetch balances + positions from Bybit V5 Unified Trading account."""

    name = "bybit"

    def __init__(self, config):
        self._config = config
        self._session = HTTP(
            testnet=False,
            api_key=config.bybit_api_key,
            api_secret=config.bybit_api_secret,
            domain="bytick",
            recv_window=5000,
        )
        if hasattr(self._session, "client"):
            self._session.client.timeout = 10

    # ── Balances ─────────────────────────────────────────────────

    async def fetch_balances(self) -> list[NormalizedBalance]:
        resp = await _retry(
            thread_with_timeout,
            self._session.get_wallet_balance,
            accountType="UNIFIED",
            timeout=_ADAPTER_TIMEOUT,
        )

        coins_list = resp.get("result", {}).get("list", [])
        ts = int(time.time() * 1000)
        balances: list[NormalizedBalance] = []

        for account in coins_list:
            total_equity = _fz(account.get("totalEquity"))
            available = _fz(account.get("totalAvailableBalance"))
            used_margin = _fz(account.get("totalInitialMargin"))
            total_pnl = _fz(account.get("totalPerpUPL"))

            # Account-level summary (unified USDT-equivalent)
            balances.append(NormalizedBalance(
                exchange="bybit",
                currency="USDT",
                total_equity=total_equity,
                available=available,
                used_margin=used_margin,
                unrealized_pnl=total_pnl,
                timestamp_ms=ts,
            ))

            # Per-coin breakdown — skip dust (<$0.01 equity)
            for coin in account.get("coin", []):
                currency = coin.get("coin", "UNKNOWN")
                if currency == "USDT":
                    continue  # already covered by account-level
                equity = _fz(coin.get("equity"))
                if equity is None or equity < 0.01:
                    continue  # skip dust
                avail = _fz(coin.get("availableToWithdraw"))
                upl = _fz(coin.get("unrealisedPnl"))
                margin = _fz(coin.get("totalPositionIM"))

                balances.append(NormalizedBalance(
                    exchange="bybit",
                    currency=currency,
                    total_equity=equity,
                    available=avail,
                    used_margin=margin,
                    unrealized_pnl=upl,
                    timestamp_ms=ts,
                ))

        return balances

    # ── Positions ────────────────────────────────────────────────

    async def fetch_positions(self) -> list[NormalizedPosition]:
        resp = await _retry(
            thread_with_timeout,
            self._session.get_positions,
            category="linear",
            settleCoin="USDT",
            timeout=_ADAPTER_TIMEOUT,
        )

        raw_list = resp.get("result", {}).get("list", [])
        ts = int(time.time() * 1000)
        positions: list[NormalizedPosition] = []

        for pos in raw_list:
            size = abs(float(pos.get("size", 0)))
            if size == 0:
                continue

            side_raw = pos.get("side", "")
            side = "LONG" if side_raw == "Buy" else "SHORT"

            positions.append(NormalizedPosition(
                exchange="bybit",
                symbol=pos.get("symbol", ""),
                market_type="linear",
                side=side,
                qty=size,
                entry_price=_f(pos.get("avgPrice")),
                mark_price=_f(pos.get("markPrice")),
                unrealized_pnl=_f(pos.get("unrealisedPnl")),
                leverage=_f(pos.get("leverage")),
                liq_price=_f(pos.get("liqPrice")),
                timestamp_ms=ts,
            ))

        return positions


# ─── Lighter Adapter ────────────────────────────────────────────

class LighterAdapter:
    """Fetch balances + positions from Lighter DEX REST API."""

    name = "lighter"

    def __init__(self, config):
        self._config = config
        self._base_url = config.lighter_base_url
        self._account_index = config.lighter_account_index

    # ── Balances ─────────────────────────────────────────────────

    async def fetch_balances(self) -> list[NormalizedBalance]:
        import aiohttp

        url = f"{self._base_url}/api/v1/account"
        params = {"by": "index", "value": str(self._account_index)}
        ts = int(time.time() * 1000)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=_ADAPTER_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Lighter /account returned {resp.status}")
                data = await resp.json()

        accounts = data.get("accounts", [])
        if not accounts:
            return []

        acct = accounts[0]
        collateral = _fz(acct.get("collateral"))
        available = _fz(acct.get("available_balance"))

        # Sum unrealized PnL from all positions (not available at account level)
        total_upnl = 0.0
        for p in acct.get("positions", []):
            upnl = _fz(p.get("unrealized_pnl"))
            if upnl is not None:
                total_upnl += upnl

        return [NormalizedBalance(
            exchange="lighter",
            currency="USDT",
            total_equity=collateral,
            available=available,
            used_margin=_safe_sub(collateral, available),
            unrealized_pnl=total_upnl,
            timestamp_ms=ts,
        )]

    # ── Positions ────────────────────────────────────────────────

    async def fetch_positions(self) -> list[NormalizedPosition]:
        import aiohttp

        url = f"{self._base_url}/api/v1/account"
        params = {"by": "index", "value": str(self._account_index)}
        ts = int(time.time() * 1000)

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=_ADAPTER_TIMEOUT)
        ) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Lighter /account returned {resp.status}")
                data = await resp.json()

        accounts = data.get("accounts", [])
        if not accounts:
            return []

        raw_positions = accounts[0].get("positions", [])
        positions: list[NormalizedPosition] = []

        for p in raw_positions:
            raw_size = float(p.get("position", "0"))
            if raw_size == 0:
                continue

            sign = p.get("sign", 1)
            is_long = (sign == 1)
            if raw_size < 0:
                is_long = False
                raw_size = abs(raw_size)

            # Map Lighter short symbol → dashboard symbol
            # Step 1: "XAU" → "XAUUSDT" via LIGHTER_SYM_TO_NORMALIZED
            # Step 2: "XAUUSDT" → "XAUTUSDT" via reverse lighter_aliases
            from app.collectors.lighter_collector import LIGHTER_SYM_TO_NORMALIZED
            lighter_sym = p.get("symbol", "")
            normalized = LIGHTER_SYM_TO_NORMALIZED.get(lighter_sym.upper(), lighter_sym)
            reverse_aliases = {v: k for k, v in self._config.lighter_aliases.items()}
            dashboard_sym = reverse_aliases.get(normalized, normalized)

            positions.append(NormalizedPosition(
                exchange="lighter",
                symbol=dashboard_sym,
                market_type="linear",
                side="LONG" if is_long else "SHORT",
                qty=raw_size,
                entry_price=_f(p.get("avg_entry_price")),
                mark_price=_f(p.get("mark_price")),
                unrealized_pnl=_f(p.get("unrealized_pnl")),
                leverage=None,   # Lighter doesn't expose per-position leverage
                liq_price=_f(p.get("liquidation_price")),
                timestamp_ms=ts,
            ))

        return positions


# ─── Utility ─────────────────────────────────────────────────────

def _f(val) -> float | None:
    """Safely parse a value to float, returning None on failure/empty.
    Returns None for zero values (meaning 'no data')."""
    if val is None or val == "":
        return None
    try:
        v = float(val)
        return v if v != 0 else None
    except (ValueError, TypeError):
        return None


def _fz(val) -> float | None:
    """Like _f but preserves zero as a valid value (for balances/margins)."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_sub(a: float | None, b: float | None) -> float | None:
    """Subtract two optional floats."""
    if a is None or b is None:
        return None
    return round(a - b, 4)
