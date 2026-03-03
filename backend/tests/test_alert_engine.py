# file: backend/tests/test_alert_engine.py
"""
Tests for alert_engine state machine.
Mocks telegram_notifier.send_telegram to avoid real API calls.
"""
import asyncio
import time

import pytest
from unittest.mock import AsyncMock, patch

from app.models import SpreadMetric
from app.alerts.alert_engine import (
    on_spread_update,
    AlertState,
    _get_state,
    _compute_metric_bps,
)


def _make_spread(
    symbol: str = "BTCUSDT",
    long_spread: float = 0.0,
    short_spread: float = 0.0,
) -> SpreadMetric:
    """Helper to build a SpreadMetric with controlled spread values."""
    return SpreadMetric(
        ts=time.time() * 1000,
        symbol=symbol,
        bybit_mid=50000.0,
        lighter_mid=50000.0,
        bybit_bid=49999.0,
        bybit_ask=50001.0,
        lighter_bid=49999.0,
        lighter_ask=50001.0,
        exchange_spread_mid=0.0,
        long_spread=long_spread,
        short_spread=short_spread,
        bid_ask_spread_bybit=0.00004,
        bid_ask_spread_lighter=0.00004,
        received_at=time.time() * 1000,
    )


class TestComputeMetricBps:
    def test_long_dominant(self):
        spread = _make_spread(long_spread=0.007, short_spread=0.003)
        bps, side = _compute_metric_bps(spread)
        assert bps == pytest.approx(70.0)
        assert side == "LONG"

    def test_short_dominant(self):
        spread = _make_spread(long_spread=0.002, short_spread=-0.008)
        bps, side = _compute_metric_bps(spread)
        assert bps == pytest.approx(80.0)
        assert side == "SHORT"

    def test_negative_long(self):
        spread = _make_spread(long_spread=-0.006, short_spread=0.003)
        bps, side = _compute_metric_bps(spread)
        assert bps == pytest.approx(60.0)
        assert side == "LONG"

    def test_equal_sides_prefers_long(self):
        spread = _make_spread(long_spread=0.005, short_spread=-0.005)
        bps, side = _compute_metric_bps(spread)
        assert bps == pytest.approx(50.0)
        assert side == "LONG"


@pytest.mark.asyncio
class TestStateTransitions:

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_normal_to_alerting(self, mock_settings, mock_insert, mock_send):
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0
        mock_send.return_value = True

        spread = _make_spread(long_spread=0.007)  # 70 bps > 60
        await on_spread_update(spread)
        await asyncio.sleep(0.1)  # let fire-and-forget task complete

        state = _get_state("BTCUSDT")
        assert state.state == AlertState.ALERTING
        mock_send.assert_called_once()
        mock_insert.assert_called_once()

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_alerting_to_normal(self, mock_settings, mock_insert, mock_send):
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0
        mock_send.return_value = True

        # First trigger alert
        await on_spread_update(_make_spread(long_spread=0.007))
        await asyncio.sleep(0.1)
        mock_send.reset_mock()
        mock_insert.reset_mock()

        # Now recover
        await on_spread_update(_make_spread(long_spread=0.002))  # 20 bps < 30
        await asyncio.sleep(0.1)

        state = _get_state("BTCUSDT")
        assert state.state == AlertState.NORMAL
        mock_send.assert_called_once()
        call_text = mock_send.call_args[0][0]
        assert "SPREAD NORMAL" in call_text

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_no_transition_in_dead_zone(self, mock_settings, mock_insert, mock_send):
        """Between upper (60) and lower (30) thresholds, no transition occurs."""
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0
        mock_send.return_value = True

        # Trigger alert first
        await on_spread_update(_make_spread(long_spread=0.007))  # 70 bps
        await asyncio.sleep(0.1)
        mock_send.reset_mock()

        # Drop to 45 bps — still in dead zone, should stay ALERTING
        await on_spread_update(_make_spread(long_spread=0.0045))
        await asyncio.sleep(0.1)

        state = _get_state("BTCUSDT")
        assert state.state == AlertState.ALERTING
        mock_send.assert_not_called()

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_cooldown_prevents_repeat(self, mock_settings, mock_insert, mock_send):
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 9999  # very long cooldown
        mock_send.return_value = True

        # Trigger alert
        await on_spread_update(_make_spread(long_spread=0.007))
        await asyncio.sleep(0.1)
        mock_send.reset_mock()

        # Recover — state transitions but no send due to cooldown
        await on_spread_update(_make_spread(long_spread=0.002))
        await asyncio.sleep(0.1)

        state = _get_state("BTCUSDT")
        assert state.state == AlertState.NORMAL
        mock_send.assert_not_called()

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_disabled_does_nothing(self, mock_settings, mock_insert, mock_send):
        mock_settings.telegram_enabled = False

        await on_spread_update(_make_spread(long_spread=0.007))
        await asyncio.sleep(0.1)

        mock_send.assert_not_called()
        mock_insert.assert_not_called()

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_multi_symbol_independent(self, mock_settings, mock_insert, mock_send):
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0
        mock_send.return_value = True

        # Alert BTC, keep ETH normal
        await on_spread_update(_make_spread("BTCUSDT", long_spread=0.007))
        await on_spread_update(_make_spread("ETHUSDT", long_spread=0.003))
        await asyncio.sleep(0.1)

        assert _get_state("BTCUSDT").state == AlertState.ALERTING
        assert _get_state("ETHUSDT").state == AlertState.NORMAL

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_below_upper_stays_normal(self, mock_settings, mock_insert, mock_send):
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0

        await on_spread_update(_make_spread(long_spread=0.005))  # 50 bps < 60
        await asyncio.sleep(0.1)

        state = _get_state("BTCUSDT")
        assert state.state == AlertState.NORMAL
        mock_send.assert_not_called()
