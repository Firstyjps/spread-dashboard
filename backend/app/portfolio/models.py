"""
Normalized portfolio data models.

Exchange-agnostic representations of balances, positions, and snapshots.
Every adapter normalizes raw exchange data into these models before returning.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field


# ─── Normalized Balance ──────────────────────────────────────────

@dataclass
class NormalizedBalance:
    exchange: str
    currency: str                          # e.g. "USDT"
    total_equity: float | None = None      # total wallet equity
    available: float | None = None         # available / withdrawable
    used_margin: float | None = None       # margin in use
    unrealized_pnl: float | None = None
    timestamp_ms: int = 0

    def __post_init__(self):
        if self.timestamp_ms == 0:
            self.timestamp_ms = int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "currency": self.currency,
            "total_equity": self.total_equity,
            "available": self.available,
            "used_margin": self.used_margin,
            "unrealized_pnl": self.unrealized_pnl,
            "timestamp_ms": self.timestamp_ms,
        }


# ─── Normalized Position ────────────────────────────────────────

@dataclass
class NormalizedPosition:
    exchange: str
    symbol: str
    market_type: str = "linear"            # "linear" | "spot" | "other"
    side: str = "LONG"                     # "LONG" | "SHORT"
    qty: float = 0.0
    entry_price: float | None = None
    mark_price: float | None = None
    unrealized_pnl: float | None = None
    leverage: float | None = None
    liq_price: float | None = None
    timestamp_ms: int = 0

    def __post_init__(self):
        if self.timestamp_ms == 0:
            self.timestamp_ms = int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "market_type": self.market_type,
            "side": self.side,
            "qty": self.qty,
            "entry_price": self.entry_price,
            "mark_price": self.mark_price,
            "unrealized_pnl": self.unrealized_pnl,
            "leverage": self.leverage,
            "liq_price": self.liq_price,
            "timestamp_ms": self.timestamp_ms,
        }


# ─── Per-Exchange Snapshot ──────────────────────────────────────

@dataclass
class ExchangePortfolioSnapshot:
    exchange: str
    balances: list[NormalizedBalance] = field(default_factory=list)
    positions: list[NormalizedPosition] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "exchange": self.exchange,
            "balances": [b.to_dict() for b in self.balances],
            "positions": [p.to_dict() for p in self.positions],
            "errors": self.errors,
        }


# ─── Aggregated Portfolio Snapshot ──────────────────────────────

@dataclass
class PortfolioSnapshot:
    snapshots: list[ExchangePortfolioSnapshot] = field(default_factory=list)

    @property
    def totals(self) -> dict:
        """Aggregate totals across all exchanges (USDT only)."""
        total_equity = 0.0
        total_available = 0.0
        total_used_margin = 0.0
        total_unrealized_pnl = 0.0
        has_data = False

        for snap in self.snapshots:
            for b in snap.balances:
                if b.currency.upper() != "USDT":
                    continue
                has_data = True
                if b.total_equity is not None:
                    total_equity += b.total_equity
                if b.available is not None:
                    total_available += b.available
                if b.used_margin is not None:
                    total_used_margin += b.used_margin
                if b.unrealized_pnl is not None:
                    total_unrealized_pnl += b.unrealized_pnl

        if not has_data:
            return {}

        return {
            "currency": "USDT",
            "total_equity": round(total_equity, 4),
            "available": round(total_available, 4),
            "used_margin": round(total_used_margin, 4),
            "unrealized_pnl": round(total_unrealized_pnl, 4),
        }

    def to_dict(self) -> dict:
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "totals": self.totals,
        }
