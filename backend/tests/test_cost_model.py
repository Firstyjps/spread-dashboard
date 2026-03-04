# file: backend/tests/test_cost_model.py
"""Tests for transaction cost model."""
import pytest
from app.analytics.cost_model import estimate_net_pnl_bps, is_profitable


class TestEstimateNetPnlBps:
    def test_profitable_wide_spread(self):
        """65 bps spread (XAUT-typical) minus 3 bps cost = 62 bps profit."""
        assert estimate_net_pnl_bps(65.0) == 62.0

    def test_profitable_moderate_spread(self):
        """10 bps spread minus 3 bps cost = 7 bps."""
        assert estimate_net_pnl_bps(10.0) == 7.0

    def test_unprofitable_tight_spread(self):
        """2 bps spread minus 3 bps cost = -1 bps."""
        assert estimate_net_pnl_bps(2.0) == -1.0

    def test_breakeven(self):
        """3 bps spread minus 3 bps cost = 0."""
        assert estimate_net_pnl_bps(3.0) == 0.0

    def test_negative_spread_uses_abs(self):
        """Negative spread still uses absolute value."""
        assert estimate_net_pnl_bps(-10.0) == 7.0

    def test_custom_fees(self):
        """Custom fee override."""
        result = estimate_net_pnl_bps(10.0, bybit_fee_bps=5.5, lighter_fee_bps=1.0, slippage_bps=2.0)
        assert result == 1.5  # 10 - 5.5 - 1.0 - 2.0

    def test_zero_fees(self):
        """Zero fees = gross = net."""
        assert estimate_net_pnl_bps(15.0, bybit_fee_bps=0, lighter_fee_bps=0, slippage_bps=0) == 15.0

    def test_hype_typical(self):
        """HYPE-typical spread: 4 bps minus 3 bps cost = 1 bps."""
        assert estimate_net_pnl_bps(4.0) == 1.0

    def test_rounding(self):
        """Result is rounded to 2 decimal places."""
        # 3.333 bps spread - 3.0 cost = 0.333... -> 0.33
        result = estimate_net_pnl_bps(3.333)
        assert result == 0.33

    def test_zero_spread(self):
        """Zero spread = pure cost."""
        assert estimate_net_pnl_bps(0.0) == -3.0


class TestIsProfitable:
    def test_profitable(self):
        assert is_profitable(65.0) is True

    def test_unprofitable(self):
        assert is_profitable(2.0) is False

    def test_breakeven_is_not_profitable(self):
        """Exactly zero net PnL is not profitable (strict >0)."""
        assert is_profitable(3.0) is False
