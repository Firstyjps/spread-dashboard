# file: backend/tests/test_settings_thresholds.py
"""Tests for per-symbol alert threshold overrides in Settings."""
import pytest
from app.config.settings import Settings


def _make_settings(**kwargs) -> Settings:
    """Create Settings with overrides, bypassing .env file."""
    defaults = {
        "alert_upper_bps": 9.0,
        "alert_lower_bps": -1.0,
        "alert_overrides": "",
    }
    defaults.update(kwargs)
    return Settings(**defaults, _env_file=None)


class TestGetAlertThresholds:
    def test_global_defaults(self):
        s = _make_settings()
        upper, lower = s.get_alert_thresholds("HYPEUSDT")
        assert upper == 9.0
        assert lower == -1.0

    def test_single_override(self):
        s = _make_settings(alert_overrides="XAUTUSDT:75:45")
        upper, lower = s.get_alert_thresholds("XAUTUSDT")
        assert upper == 75.0
        assert lower == 45.0

    def test_override_symbol_not_found_uses_global(self):
        s = _make_settings(alert_overrides="XAUTUSDT:75:45")
        upper, lower = s.get_alert_thresholds("HYPEUSDT")
        assert upper == 9.0
        assert lower == -1.0

    def test_multiple_overrides(self):
        s = _make_settings(alert_overrides="XAUTUSDT:75:45,BTCUSDT:15:5")
        xu, xl = s.get_alert_thresholds("XAUTUSDT")
        assert xu == 75.0
        assert xl == 45.0
        bu, bl = s.get_alert_thresholds("BTCUSDT")
        assert bu == 15.0
        assert bl == 5.0
        # Not overridden
        hu, hl = s.get_alert_thresholds("ETHUSDT")
        assert hu == 9.0
        assert hl == -1.0

    def test_whitespace_handling(self):
        s = _make_settings(alert_overrides=" XAUTUSDT : 75 : 45 , BTCUSDT:15:5 ")
        upper, lower = s.get_alert_thresholds("XAUTUSDT")
        assert upper == 75.0
        assert lower == 45.0

    def test_empty_string(self):
        s = _make_settings(alert_overrides="")
        upper, lower = s.get_alert_thresholds("XAUTUSDT")
        assert upper == 9.0
        assert lower == -1.0

    def test_malformed_entries_skipped(self):
        """Entries with wrong number of parts are silently skipped."""
        s = _make_settings(alert_overrides="BAD_ENTRY,XAUTUSDT:75:45,ALSO:BAD")
        upper, lower = s.get_alert_thresholds("XAUTUSDT")
        assert upper == 75.0
        assert lower == 45.0
        # BAD_ENTRY falls through to global
        bu, bl = s.get_alert_thresholds("BAD_ENTRY")
        assert bu == 9.0
        assert bl == -1.0

    def test_non_numeric_values_skipped(self):
        """Non-numeric values in override are skipped, falls back to global."""
        s = _make_settings(alert_overrides="XAUTUSDT:abc:45")
        upper, lower = s.get_alert_thresholds("XAUTUSDT")
        assert upper == 9.0
        assert lower == -1.0

    def test_float_values(self):
        s = _make_settings(alert_overrides="XAUTUSDT:75.5:45.3")
        upper, lower = s.get_alert_thresholds("XAUTUSDT")
        assert upper == 75.5
        assert lower == 45.3

    def test_negative_lower(self):
        """Global default lower is -1.0, overrides can also be negative."""
        s = _make_settings(alert_overrides="BTCUSDT:10:-2")
        upper, lower = s.get_alert_thresholds("BTCUSDT")
        assert upper == 10.0
        assert lower == -2.0
