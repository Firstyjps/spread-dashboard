"""
Tests for the portfolio module.

1) Normalization of Bybit positions
2) Portfolio orchestrator returns multiple exchanges
3) Partial failure handling (one exchange errors, still returns others)
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.portfolio.models import (
    NormalizedBalance,
    NormalizedPosition,
    ExchangePortfolioSnapshot,
    PortfolioSnapshot,
)
from app.portfolio.adapters import BybitLinearAdapter, LighterAdapter, _f, _fz
from app.portfolio.service import fetch_portfolio_snapshot, _fetch_one


# ─── Fixtures: mock Bybit raw responses ─────────────────────────

BYBIT_WALLET_RESPONSE = {
    "retCode": 0,
    "result": {
        "list": [
            {
                "totalEquity": "12345.6789",
                "totalAvailableBalance": "9000.1234",
                "totalInitialMargin": "3345.5555",
                "totalPerpUPL": "123.45",
                "coin": [
                    {
                        "coin": "USDT",
                        "equity": "12345.6789",
                        "availableToWithdraw": "9000.1234",
                        "unrealisedPnl": "123.45",
                        "totalPositionIM": "3345.5555",
                    }
                ],
            }
        ]
    },
}

BYBIT_POSITIONS_RESPONSE = {
    "retCode": 0,
    "result": {
        "list": [
            {
                "symbol": "HYPEUSDT",
                "side": "Sell",
                "size": "10.0",
                "avgPrice": "30.470",
                "markPrice": "30.450",
                "unrealisedPnl": "0.20",
                "leverage": "5",
                "liqPrice": "35.000",
            },
            {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": "0.05",
                "avgPrice": "98000.0",
                "markPrice": "98500.0",
                "unrealisedPnl": "25.0",
                "leverage": "10",
                "liqPrice": "85000.0",
            },
            {
                # Zero-size position should be filtered out
                "symbol": "ETHUSDT",
                "side": "Buy",
                "size": "0",
                "avgPrice": "0",
            },
        ]
    },
}


# ─── Test: _f helper ────────────────────────────────────────────

class TestParseFloat:
    def test_valid_float(self):
        assert _f("123.45") == 123.45

    def test_zero_returns_none(self):
        assert _f("0") is None
        assert _f(0) is None

    def test_empty_returns_none(self):
        assert _f("") is None
        assert _f(None) is None

    def test_invalid_returns_none(self):
        assert _f("abc") is None

    def test_fz_preserves_zero(self):
        assert _fz("0") == 0.0
        assert _fz(0) == 0.0
        assert _fz("0.00") == 0.0

    def test_fz_none_on_empty(self):
        assert _fz("") is None
        assert _fz(None) is None


# ─── Test: Bybit position normalization ─────────────────────────

class TestBybitNormalization:
    @pytest.fixture
    def adapter(self):
        config = MagicMock()
        config.bybit_api_key = "test"
        config.bybit_api_secret = "test"
        with patch("app.portfolio.adapters.HTTP"):
            return BybitLinearAdapter(config)

    @pytest.mark.asyncio
    async def test_positions_normalized(self, adapter):
        """Bybit positions are correctly normalized: side, qty, fields."""
        adapter._session = MagicMock()

        async def mock_thread(fn, *a, **kw):
            return BYBIT_POSITIONS_RESPONSE

        with patch("app.portfolio.adapters.thread_with_timeout", side_effect=mock_thread):
            positions = await adapter.fetch_positions()

        # Zero-size ETHUSDT should be filtered out
        assert len(positions) == 2

        # HYPEUSDT — Sell → SHORT
        hype = positions[0]
        assert hype.exchange == "bybit"
        assert hype.symbol == "HYPEUSDT"
        assert hype.side == "SHORT"
        assert hype.qty == 10.0
        assert hype.entry_price == 30.470
        assert hype.mark_price == 30.450
        assert hype.leverage == 5.0
        assert hype.market_type == "linear"

        # BTCUSDT — Buy → LONG
        btc = positions[1]
        assert btc.side == "LONG"
        assert btc.qty == 0.05
        assert btc.entry_price == 98000.0

    @pytest.mark.asyncio
    async def test_balances_normalized(self, adapter):
        """Bybit wallet balance is correctly normalized."""
        adapter._session = MagicMock()

        async def mock_thread(fn, *a, **kw):
            return BYBIT_WALLET_RESPONSE

        with patch("app.portfolio.adapters.thread_with_timeout", side_effect=mock_thread):
            balances = await adapter.fetch_balances()

        assert len(balances) == 1
        b = balances[0]
        assert b.exchange == "bybit"
        assert b.currency == "USDT"
        assert b.total_equity == 12345.6789
        assert b.available == 9000.1234
        assert b.used_margin == 3345.5555
        assert b.unrealized_pnl == 123.45


# ─── Test: Orchestrator multi-exchange ──────────────────────────

class TestOrchestrator:
    @pytest.mark.asyncio
    async def test_returns_multiple_exchanges(self):
        """Orchestrator returns snapshots from both exchanges."""
        mock_bybit = MagicMock()
        mock_bybit.name = "bybit"
        mock_bybit.fetch_balances = AsyncMock(return_value=[
            NormalizedBalance(exchange="bybit", currency="USDT",
                              total_equity=10000.0, available=8000.0),
        ])
        mock_bybit.fetch_positions = AsyncMock(return_value=[
            NormalizedPosition(exchange="bybit", symbol="HYPEUSDT",
                               side="SHORT", qty=10.0),
        ])

        mock_lighter = MagicMock()
        mock_lighter.name = "lighter"
        mock_lighter.fetch_balances = AsyncMock(return_value=[
            NormalizedBalance(exchange="lighter", currency="USDT",
                              total_equity=5000.0, available=4000.0),
        ])
        mock_lighter.fetch_positions = AsyncMock(return_value=[
            NormalizedPosition(exchange="lighter", symbol="HYPEUSDT",
                               side="LONG", qty=10.0),
        ])

        with patch("app.portfolio.service._get_adapters",
                    return_value={"bybit": mock_bybit, "lighter": mock_lighter}):
            snapshot = await fetch_portfolio_snapshot()

        assert len(snapshot.snapshots) == 2

        bybit_snap = next(s for s in snapshot.snapshots if s.exchange == "bybit")
        lighter_snap = next(s for s in snapshot.snapshots if s.exchange == "lighter")

        assert len(bybit_snap.balances) == 1
        assert len(bybit_snap.positions) == 1
        assert len(lighter_snap.balances) == 1
        assert len(lighter_snap.positions) == 1
        assert bybit_snap.errors == []
        assert lighter_snap.errors == []

    @pytest.mark.asyncio
    async def test_partial_failure(self):
        """If one exchange fails, the other still returns data."""
        mock_bybit = MagicMock()
        mock_bybit.name = "bybit"
        mock_bybit.fetch_balances = AsyncMock(
            side_effect=ConnectionError("Bybit API down")
        )
        mock_bybit.fetch_positions = AsyncMock(return_value=[
            NormalizedPosition(exchange="bybit", symbol="HYPEUSDT",
                               side="SHORT", qty=10.0),
        ])

        mock_lighter = MagicMock()
        mock_lighter.name = "lighter"
        mock_lighter.fetch_balances = AsyncMock(return_value=[
            NormalizedBalance(exchange="lighter", currency="USDT",
                              total_equity=5000.0),
        ])
        mock_lighter.fetch_positions = AsyncMock(return_value=[])

        with patch("app.portfolio.service._get_adapters",
                    return_value={"bybit": mock_bybit, "lighter": mock_lighter}):
            snapshot = await fetch_portfolio_snapshot()

        assert len(snapshot.snapshots) == 2

        bybit_snap = next(s for s in snapshot.snapshots if s.exchange == "bybit")
        lighter_snap = next(s for s in snapshot.snapshots if s.exchange == "lighter")

        # Bybit: balance failed, positions ok
        assert len(bybit_snap.errors) == 1
        assert "balance error" in bybit_snap.errors[0]
        assert len(bybit_snap.positions) == 1

        # Lighter: fully successful
        assert lighter_snap.errors == []
        assert len(lighter_snap.balances) == 1

    @pytest.mark.asyncio
    async def test_filter_by_exchange(self):
        """Passing exchanges= filters to only requested exchanges."""
        mock_bybit = MagicMock()
        mock_bybit.name = "bybit"
        mock_bybit.fetch_balances = AsyncMock(return_value=[])
        mock_bybit.fetch_positions = AsyncMock(return_value=[])

        mock_lighter = MagicMock()
        mock_lighter.name = "lighter"
        mock_lighter.fetch_balances = AsyncMock(return_value=[])
        mock_lighter.fetch_positions = AsyncMock(return_value=[])

        with patch("app.portfolio.service._get_adapters",
                    return_value={"bybit": mock_bybit, "lighter": mock_lighter}):
            snapshot = await fetch_portfolio_snapshot(exchanges=["bybit"])

        assert len(snapshot.snapshots) == 1
        assert snapshot.snapshots[0].exchange == "bybit"
        mock_lighter.fetch_balances.assert_not_called()


# ─── Test: Totals aggregation ───────────────────────────────────

class TestTotals:
    def test_aggregate_totals(self):
        """Portfolio totals sum USDT balances across exchanges."""
        snap = PortfolioSnapshot(snapshots=[
            ExchangePortfolioSnapshot(
                exchange="bybit",
                balances=[NormalizedBalance(
                    exchange="bybit", currency="USDT",
                    total_equity=10000.0, available=8000.0,
                    used_margin=2000.0, unrealized_pnl=100.0,
                )],
            ),
            ExchangePortfolioSnapshot(
                exchange="lighter",
                balances=[NormalizedBalance(
                    exchange="lighter", currency="USDT",
                    total_equity=5000.0, available=4000.0,
                    used_margin=1000.0, unrealized_pnl=-50.0,
                )],
            ),
        ])

        totals = snap.totals
        assert totals["currency"] == "USDT"
        assert totals["total_equity"] == 15000.0
        assert totals["available"] == 12000.0
        assert totals["used_margin"] == 3000.0
        assert totals["unrealized_pnl"] == 50.0

    def test_empty_totals(self):
        """Empty portfolio returns empty totals dict."""
        snap = PortfolioSnapshot(snapshots=[])
        assert snap.totals == {}

    def test_to_dict(self):
        """to_dict() serializes correctly."""
        snap = PortfolioSnapshot(snapshots=[
            ExchangePortfolioSnapshot(
                exchange="bybit",
                balances=[NormalizedBalance(
                    exchange="bybit", currency="USDT", total_equity=10000.0,
                )],
                positions=[NormalizedPosition(
                    exchange="bybit", symbol="HYPEUSDT", side="SHORT", qty=10.0,
                )],
            ),
        ])

        d = snap.to_dict()
        assert "snapshots" in d
        assert "totals" in d
        assert len(d["snapshots"]) == 1
        assert d["snapshots"][0]["exchange"] == "bybit"
        assert len(d["snapshots"][0]["balances"]) == 1
        assert len(d["snapshots"][0]["positions"]) == 1
