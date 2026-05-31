"""
Portfolio orchestrator — fetch balance + position snapshots from all exchanges.

Runs each exchange adapter concurrently with per-exchange timeouts.
Partial failures are captured per-exchange (others still return).
"""
from __future__ import annotations

import asyncio
import structlog

from app.config import settings
from app.portfolio.models import (
    ExchangePortfolioSnapshot,
    PortfolioSnapshot,
)
from app.portfolio.adapters import BybitLinearAdapter, LighterAdapter, ExchangeAdapter

log = structlog.get_logger()

# Per-exchange timeout for the whole fetch (balances + positions)
_EXCHANGE_TIMEOUT = 20.0

# ── Singleton adapters (lazy init, auto-recreate on key change) ──
_adapters_manual: dict[str, ExchangeAdapter] | None = None
_adapters_ai: dict[str, ExchangeAdapter] | None = None
_manual_bybit_key: str = ""
_ai_bybit_key: str = ""

def _get_adapters(account: str = "manual") -> dict[str, ExchangeAdapter]:
    global _adapters_manual, _adapters_ai, _manual_bybit_key, _ai_bybit_key
    
    if account == "ai":
        if _adapters_ai is None or _ai_bybit_key != settings.ai_bybit_api_key:
            import copy
            ai_config = copy.copy(settings)
            ai_config.bybit_api_key = settings.ai_bybit_api_key
            ai_config.bybit_api_secret = settings.ai_bybit_api_secret
            ai_config.lighter_private_key = settings.ai_lighter_private_key
            ai_config.lighter_account_index = settings.ai_lighter_account_index
            
            _adapters_ai = {
                "bybit": BybitLinearAdapter(ai_config),
                "lighter": LighterAdapter(ai_config),
            }
            _ai_bybit_key = settings.ai_bybit_api_key
        return _adapters_ai

    # Default manual
    if _adapters_manual is None or _manual_bybit_key != settings.bybit_api_key:
        _adapters_manual = {
            "bybit": BybitLinearAdapter(settings),
            "lighter": LighterAdapter(settings),
        }
        _manual_bybit_key = settings.bybit_api_key
        log.info("portfolio_adapters_recreated")
    return _adapters_manual

def reset_adapters():
    """Force-clear cached adapters so they recreate on next access."""
    global _adapters_manual, _adapters_ai, _manual_bybit_key, _ai_bybit_key
    _adapters_manual = None
    _adapters_ai = None
    _manual_bybit_key = ""
    _ai_bybit_key = ""


# ── Single-exchange fetch ────────────────────────────────────────

async def _fetch_one(adapter: ExchangeAdapter) -> ExchangePortfolioSnapshot:
    """Fetch balances + positions for a single exchange with timeout."""
    snap = ExchangePortfolioSnapshot(exchange=adapter.name)

    async def _balances():
        try:
            snap.balances = await asyncio.wait_for(
                adapter.fetch_balances(), timeout=_EXCHANGE_TIMEOUT
            )
        except asyncio.TimeoutError:
            snap.errors.append("balance fetch timed out")
            log.error("portfolio_balance_timeout", exchange=adapter.name)
        except Exception as e:
            snap.errors.append(f"balance error: {e}")
            log.error("portfolio_balance_error", exchange=adapter.name, error=str(e))

    async def _positions():
        try:
            snap.positions = await asyncio.wait_for(
                adapter.fetch_positions(), timeout=_EXCHANGE_TIMEOUT
            )
        except asyncio.TimeoutError:
            snap.errors.append("position fetch timed out")
            log.error("portfolio_position_timeout", exchange=adapter.name)
        except Exception as e:
            snap.errors.append(f"position error: {e}")
            log.error("portfolio_position_error", exchange=adapter.name, error=str(e))

    # Run balance + position fetch concurrently within the same exchange
    await asyncio.gather(_balances(), _positions())

    if not snap.errors:
        log.info("portfolio_exchange_ok", exchange=adapter.name,
                 balances=len(snap.balances), positions=len(snap.positions))

    return snap


# ── Public orchestrator ──────────────────────────────────────────

async def fetch_portfolio_snapshot(
    exchanges: list[str] | None = None,
    account: str = "manual",
) -> PortfolioSnapshot:
    """
    Fetch portfolio snapshots from all (or selected) exchanges.

    Args:
        exchanges: Optional list of exchange names to fetch.
                   None = all registered adapters.

    Returns:
        PortfolioSnapshot with per-exchange snapshots + aggregated totals.
    """
    all_adapters = _get_adapters(account)

    if exchanges:
        selected = {k: v for k, v in all_adapters.items() if k in exchanges}
    else:
        selected = all_adapters

    if not selected:
        return PortfolioSnapshot()

    log.info("portfolio_fetch_start", exchanges=list(selected.keys()))

    # Run all exchanges concurrently
    tasks = [_fetch_one(adapter) for adapter in selected.values()]
    snapshots = await asyncio.gather(*tasks)

    result = PortfolioSnapshot(snapshots=list(snapshots))

    log.info("portfolio_fetch_done",
             exchanges=len(snapshots),
             total_positions=sum(len(s.positions) for s in snapshots),
             has_errors=any(s.errors for s in snapshots))

    return result
