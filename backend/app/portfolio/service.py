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

# ── Singleton adapters (lazy init) ───────────────────────────────
_adapters: dict[str, ExchangeAdapter] | None = None


def _get_adapters() -> dict[str, ExchangeAdapter]:
    global _adapters
    if _adapters is None:
        _adapters = {
            "bybit": BybitLinearAdapter(settings),
            "lighter": LighterAdapter(settings),
        }
    return _adapters


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
) -> PortfolioSnapshot:
    """
    Fetch portfolio snapshots from all (or selected) exchanges.

    Args:
        exchanges: Optional list of exchange names to fetch.
                   None = all registered adapters.

    Returns:
        PortfolioSnapshot with per-exchange snapshots + aggregated totals.
    """
    all_adapters = _get_adapters()

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
