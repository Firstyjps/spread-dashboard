# file: backend/tests/test_alert_engine.py
"""
Tests for alert_engine state machine, side decision, and message formatting.
Mocks telegram_notifier.send_telegram to avoid real API calls.
"""
import asyncio
import time
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, patch

from app.models import SpreadMetric
from app.alerts.alert_engine import (
    on_spread_update,
    AlertState,
    _get_state,
    _compute_metric_bps,
    decide_side,
    build_alert_message,
    build_recovery_message,
    _safe_mid,
    _format_ts_bangkok,
)


def _make_spread(
    symbol: str = "BTCUSDT",
    long_spread: float = 0.0,
    short_spread: float = 0.0,
    bybit_bid: float = 49999.0,
    bybit_ask: float = 50001.0,
    lighter_bid: float = 49999.0,
    lighter_ask: float = 50001.0,
    ts: float | None = None,
) -> SpreadMetric:
    """Helper to build a SpreadMetric with controlled spread values."""
    return SpreadMetric(
        ts=ts if ts is not None else time.time() * 1000,
        symbol=symbol,
        bybit_mid=50000.0,
        lighter_mid=50000.0,
        bybit_bid=bybit_bid,
        bybit_ask=bybit_ask,
        lighter_bid=lighter_bid,
        lighter_ask=lighter_ask,
        exchange_spread_mid=0.0,
        long_spread=long_spread,
        short_spread=short_spread,
        bid_ask_spread_bybit=0.00004,
        bid_ask_spread_lighter=0.00004,
        received_at=time.time() * 1000,
    )


# ===================================================================
# _compute_metric_bps — unchanged, verify backward compat
# ===================================================================

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


# ===================================================================
# decide_side — pure function: threshold breach -> trading action
# ===================================================================

class TestDecideSide:
    def test_above_upper_returns_short(self):
        assert decide_side(61.0, upper=60.0, lower=30.0) == "SHORT"

    def test_at_upper_boundary_returns_short(self):
        assert decide_side(60.0, upper=60.0, lower=30.0) == "SHORT"

    def test_below_lower_returns_long(self):
        assert decide_side(25.0, upper=60.0, lower=30.0) == "LONG"

    def test_at_lower_boundary_returns_long(self):
        assert decide_side(30.0, upper=60.0, lower=30.0) == "LONG"

    def test_dead_zone_returns_none(self):
        assert decide_side(45.0, upper=60.0, lower=30.0) is None

    def test_just_above_lower_returns_none(self):
        assert decide_side(30.1, upper=60.0, lower=30.0) is None

    def test_just_below_upper_returns_none(self):
        assert decide_side(59.9, upper=60.0, lower=30.0) is None

    def test_custom_thresholds(self):
        assert decide_side(12.0, upper=11.0, lower=5.0) == "SHORT"
        assert decide_side(4.0, upper=11.0, lower=5.0) == "LONG"
        assert decide_side(8.0, upper=11.0, lower=5.0) is None


# ===================================================================
# _safe_mid — mid-price computation with N/A fallback
# ===================================================================

class TestSafeMid:
    def test_normal_mid(self):
        assert _safe_mid(5045.1, 5045.7) == "5045.40"

    def test_bid_none(self):
        assert _safe_mid(None, 5045.2) == "N/A"

    def test_ask_none(self):
        assert _safe_mid(5045.1, None) == "N/A"

    def test_both_none(self):
        assert _safe_mid(None, None) == "N/A"

    def test_exact_two_decimals(self):
        assert _safe_mid(100.0, 100.0) == "100.00"

    def test_rounds_to_two_decimals(self):
        # (100.1 + 100.2) / 2 = 100.15
        assert _safe_mid(100.1, 100.2) == "100.15"

    def test_large_values(self):
        assert _safe_mid(50000.0, 50002.0) == "50001.00"


# ===================================================================
# _format_ts_bangkok — UTC -> Asia/Bangkok timezone conversion
# ===================================================================

class TestFormatTsBangkok:
    def test_utc_to_bangkok_offset(self):
        """UTC 15:00 -> Bangkok 22:00 (UTC+7)"""
        dt = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        assert _format_ts_bangkok(dt) == "03-Mar-26 22:00 GMT+7"

    def test_midnight_utc(self):
        """UTC 00:00 -> Bangkok 07:00"""
        dt = datetime(2026, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        assert _format_ts_bangkok(dt) == "15-Jan-26 07:00 GMT+7"

    def test_date_rolls_over(self):
        """UTC 20:00 -> Bangkok 03:00 next day"""
        dt = datetime(2026, 6, 30, 20, 0, 0, tzinfo=timezone.utc)
        assert _format_ts_bangkok(dt) == "01-Jul-26 03:00 GMT+7"

    def test_format_has_no_seconds(self):
        dt = datetime(2026, 3, 3, 15, 30, 45, tzinfo=timezone.utc)
        result = _format_ts_bangkok(dt)
        # Must end with HH:MM GMT+7 — no seconds
        assert result == "03-Mar-26 22:30 GMT+7"

    def test_leading_zero_day(self):
        dt = datetime(2026, 12, 5, 10, 0, 0, tzinfo=timezone.utc)
        assert _format_ts_bangkok(dt) == "05-Dec-26 17:00 GMT+7"


# ===================================================================
# build_alert_message — exact output validation
# ===================================================================

class TestBuildAlertMessage:
    def test_exact_format_upper_breach(self):
        """Matches the TARGET FORMAT from the specification exactly."""
        ts = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        msg = build_alert_message(
            symbol="XAUUSDT",
            spread_bps=61.0,
            upper_bps=60.0,
            lower_bps=30.0,
            side="SHORT",
            bybit_bid=5045.1,
            bybit_ask=5045.7,
            lighter_bid=5075.0,
            lighter_ask=5075.4,
            ts_utc=ts,
        )
        expected = (
            "\U0001f6a8 <b>SPREAD ALERT XAUUSDT</b>\n"
            "metric=61.00 bps (upper=60.00)\n"
            "side=SHORT\n"
            "bybit mid=5045.40\n"
            "lighter mid=5075.20\n"
            "03-Mar-26 22:00 GMT+7"
        )
        assert msg == expected

    def test_two_decimal_formatting(self):
        """Integer-like values still get .00"""
        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        msg = build_alert_message(
            symbol="BTCUSDT",
            spread_bps=70.0,
            upper_bps=60.0,
            lower_bps=30.0,
            side="SHORT",
            bybit_bid=50000.0,
            bybit_ask=50000.0,
            lighter_bid=50035.0,
            lighter_ask=50035.0,
            ts_utc=ts,
        )
        assert "metric=70.00 bps (upper=60.00)" in msg
        assert "bybit mid=50000.00" in msg
        assert "lighter mid=50035.00" in msg

    def test_missing_bid_ask_shows_na(self):
        ts = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        msg = build_alert_message(
            symbol="XAUUSDT",
            spread_bps=61.0,
            upper_bps=60.0,
            lower_bps=30.0,
            side="SHORT",
            bybit_bid=None,
            bybit_ask=None,
            lighter_bid=5075.0,
            lighter_ask=None,
            ts_utc=ts,
        )
        assert "bybit mid=N/A" in msg
        assert "lighter mid=N/A" in msg

    def test_side_is_short_when_upper_breach(self):
        """When spread >= upper, the side passed in should be SHORT."""
        ts = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        side = decide_side(65.0, upper=60.0, lower=30.0)
        assert side == "SHORT"
        msg = build_alert_message(
            symbol="XAUUSDT",
            spread_bps=65.0,
            upper_bps=60.0,
            lower_bps=30.0,
            side=side,
            bybit_bid=5045.0,
            bybit_ask=5046.0,
            lighter_bid=5075.0,
            lighter_ask=5076.0,
            ts_utc=ts,
        )
        assert "side=SHORT" in msg

    def test_no_extra_commentary(self):
        """Alert must be compact — no parenthetical logic explanations."""
        ts = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        msg = build_alert_message(
            symbol="XAUUSDT",
            spread_bps=61.0,
            upper_bps=60.0,
            lower_bps=30.0,
            side="SHORT",
            bybit_bid=5045.0,
            bybit_ask=5046.0,
            lighter_bid=5075.0,
            lighter_ask=5076.0,
            ts_utc=ts,
        )
        assert "Logic" not in msg
        assert "bid/ask" not in msg
        assert "ts=" not in msg
        # Exactly 6 lines
        assert msg.count("\n") == 5

    def test_line_count_and_order(self):
        ts = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        msg = build_alert_message(
            symbol="TEST",
            spread_bps=61.0,
            upper_bps=60.0,
            lower_bps=30.0,
            side="SHORT",
            bybit_bid=100.0,
            bybit_ask=100.0,
            lighter_bid=200.0,
            lighter_ask=200.0,
            ts_utc=ts,
        )
        lines = msg.split("\n")
        assert len(lines) == 6
        assert lines[0].startswith("\U0001f6a8")
        assert lines[1].startswith("metric=")
        assert lines[2].startswith("side=")
        assert lines[3].startswith("bybit mid=")
        assert lines[4].startswith("lighter mid=")
        assert lines[5].endswith("GMT+7")


# ===================================================================
# build_recovery_message — exact output validation
# ===================================================================

class TestBuildRecoveryMessage:
    def test_exact_format(self):
        ts = datetime(2026, 3, 3, 16, 30, 0, tzinfo=timezone.utc)
        msg = build_recovery_message(
            symbol="XAUUSDT",
            spread_bps=25.0,
            lower_bps=30.0,
            bybit_bid=5045.1,
            bybit_ask=5045.7,
            lighter_bid=5055.0,
            lighter_ask=5055.4,
            ts_utc=ts,
        )
        expected = (
            "\u2705 <b>SPREAD NORMAL XAUUSDT</b>\n"
            "metric=25.00 bps (lower=30.00)\n"
            "bybit mid=5045.40\n"
            "lighter mid=5055.20\n"
            "03-Mar-26 23:30 GMT+7"
        )
        assert msg == expected

    def test_no_side_in_recovery(self):
        ts = datetime(2026, 3, 3, 15, 0, 0, tzinfo=timezone.utc)
        msg = build_recovery_message(
            symbol="XAUUSDT",
            spread_bps=20.0,
            lower_bps=30.0,
            bybit_bid=5045.0,
            bybit_ask=5046.0,
            lighter_bid=5075.0,
            lighter_ask=5076.0,
            ts_utc=ts,
        )
        assert "side=" not in msg

    def test_two_decimal_formatting(self):
        ts = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        msg = build_recovery_message(
            symbol="BTCUSDT",
            spread_bps=20.0,
            lower_bps=30.0,
            bybit_bid=50000.0,
            bybit_ask=50000.0,
            lighter_bid=50000.0,
            lighter_ask=50000.0,
            ts_utc=ts,
        )
        assert "metric=20.00 bps (lower=30.00)" in msg
        assert "bybit mid=50000.00" in msg


# ===================================================================
# Integration: state machine transitions (mocked Telegram)
# ===================================================================

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
    async def test_alert_message_has_side_short(self, mock_settings, mock_insert, mock_send):
        """When upper threshold breached, message must contain side=SHORT."""
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0
        mock_send.return_value = True

        spread = _make_spread(long_spread=0.007)  # 70 bps > 60
        await on_spread_update(spread)
        await asyncio.sleep(0.1)

        call_text = mock_send.call_args[0][0]
        assert "side=SHORT" in call_text
        assert "side=LONG" not in call_text

    @patch("app.alerts.alert_engine.send_telegram", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.insert_alert", new_callable=AsyncMock)
    @patch("app.alerts.alert_engine.settings")
    async def test_alert_message_format(self, mock_settings, mock_insert, mock_send):
        """Alert message must use mid prices, 2dp, and Bangkok TZ."""
        mock_settings.telegram_enabled = True
        mock_settings.alert_upper_bps = 60.0
        mock_settings.alert_lower_bps = 30.0
        mock_settings.telegram_alert_cooldown_s = 0
        mock_send.return_value = True

        spread = _make_spread(
            long_spread=0.007,
            bybit_bid=5045.1,
            bybit_ask=5045.7,
            lighter_bid=5075.0,
            lighter_ask=5075.4,
        )
        await on_spread_update(spread)
        await asyncio.sleep(0.1)

        call_text = mock_send.call_args[0][0]
        # Must use mid, not bid/ask
        assert "bybit mid=5045.40" in call_text
        assert "lighter mid=5075.20" in call_text
        assert "bid/ask" not in call_text
        # Must use 2 decimal places
        assert "metric=70.00 bps (upper=60.00)" in call_text
        # Must end with Bangkok TZ
        assert call_text.endswith("GMT+7")

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
        assert "metric=20.00 bps (lower=30.00)" in call_text

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
