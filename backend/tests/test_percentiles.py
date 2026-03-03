"""Tests for percentile computation utility."""

import math
import pytest
from app.utils.percentiles import compute_percentiles, SpreadStats, _linear_percentile


# ─── _linear_percentile (low-level) ──────────────────────────────────────


class TestLinearPercentile:
    """Verify the interpolation matches expected values."""

    def test_single_value(self):
        assert _linear_percentile([5.0], 10) == 5.0
        assert _linear_percentile([5.0], 90) == 5.0

    def test_two_values(self):
        # [1, 10]: P10 = 1 + 0.1*(10-1) = 1.9
        assert _linear_percentile([1.0, 10.0], 10) == pytest.approx(1.9)
        # [1, 10]: P90 = 1 + 0.9*(10-1) = 9.1
        assert _linear_percentile([1.0, 10.0], 90) == pytest.approx(9.1)

    def test_deterministic_10_values(self):
        # sorted: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        vals = list(range(1, 11))
        # P10: idx = 9 * 0.10 = 0.9 → 1 + 0.9*(2-1) = 1.9
        assert _linear_percentile(vals, 10) == pytest.approx(1.9)
        # P50: idx = 9 * 0.50 = 4.5 → 5 + 0.5*(6-5) = 5.5
        assert _linear_percentile(vals, 50) == pytest.approx(5.5)
        # P90: idx = 9 * 0.90 = 8.1 → 9 + 0.1*(10-9) = 9.1
        assert _linear_percentile(vals, 90) == pytest.approx(9.1)

    def test_p0_and_p100(self):
        vals = [10.0, 20.0, 30.0]
        assert _linear_percentile(vals, 0) == 10.0
        assert _linear_percentile(vals, 100) == 30.0


# ─── compute_percentiles ─────────────────────────────────────────────────


class TestComputePercentiles:
    """End-to-end tests for the public compute_percentiles function."""

    def test_deterministic_dataset(self):
        """100 evenly spaced values → known P10/P90."""
        values = [i / 100.0 for i in range(100)]  # 0.00 .. 0.99
        stats = compute_percentiles(values, min_n=10)
        # P10: idx = 99 * 0.10 = 9.9 → sorted[9] + 0.9*(sorted[10]-sorted[9])
        #   = 0.09 + 0.9 * 0.01 = 0.099
        assert stats.p10 == pytest.approx(0.099, abs=1e-6)
        # P90: idx = 99 * 0.90 = 89.1 → sorted[89] + 0.1*(sorted[90]-sorted[89])
        #   = 0.89 + 0.1 * 0.01 = 0.891
        assert stats.p90 == pytest.approx(0.891, abs=1e-6)
        assert stats.n == 100
        assert stats.mean is not None

    def test_nulls_ignored(self):
        """None values should be filtered out."""
        values = [None, 1.0, None, 2.0, 3.0, 4.0, 5.0, None] + list(range(6, 25))
        stats = compute_percentiles(values, min_n=5)
        # Only non-None values should be counted
        assert stats.n == 24  # 5 non-None + 19 from range(6,25)
        assert stats.p10 is not None
        assert stats.p90 is not None

    def test_nans_ignored(self):
        """NaN values should be filtered out."""
        values = [float("nan"), 1.0, float("nan"), 2.0] + list(range(3, 25))
        stats = compute_percentiles(values, min_n=5)
        assert stats.n == 24  # 2 non-NaN + 22 from range(3,25)
        assert stats.p10 is not None
        assert stats.p90 is not None

    def test_small_sample_returns_none(self):
        """Fewer than min_n samples → stats are None."""
        values = [1.0, 2.0, 3.0]
        stats = compute_percentiles(values, min_n=20)
        assert stats.p10 is None
        assert stats.p90 is None
        assert stats.mean is None
        assert stats.n == 3

    def test_empty_list(self):
        stats = compute_percentiles([])
        assert stats.p10 is None
        assert stats.p90 is None
        assert stats.n == 0

    def test_all_none(self):
        stats = compute_percentiles([None, None, None])
        assert stats.p10 is None
        assert stats.n == 0

    def test_all_same_value(self):
        """If all values are identical, P10 == P90 == that value."""
        values = [42.0] * 50
        stats = compute_percentiles(values, min_n=10)
        assert stats.p10 == pytest.approx(42.0)
        assert stats.p90 == pytest.approx(42.0)
        assert stats.mean == pytest.approx(42.0)

    def test_p10_less_than_p90(self):
        """P10 should always be <= P90 for any valid dataset."""
        import random
        random.seed(42)
        values = [random.gauss(0, 1) for _ in range(200)]
        stats = compute_percentiles(values, min_n=10)
        assert stats.p10 is not None
        assert stats.p90 is not None
        assert stats.p10 <= stats.p90

    def test_negative_values(self):
        """Spread values can be negative (lighter < bybit)."""
        values = [-0.005, -0.003, -0.001, 0.001, 0.003] * 10  # 50 points
        stats = compute_percentiles(values, min_n=10)
        assert stats.p10 is not None
        assert stats.p10 < 0  # most values are negative
        assert stats.p90 is not None
        assert stats.n == 50

    def test_default_min_n_is_20(self):
        """Default min_n should be 20."""
        values = list(range(19))
        stats = compute_percentiles(values)
        assert stats.p10 is None  # 19 < 20
        values.append(19)
        stats = compute_percentiles(values)
        assert stats.p10 is not None  # 20 >= 20

    def test_to_dict_format(self):
        """to_dict should produce JSON-serializable output."""
        values = [i * 0.001 for i in range(100)]
        stats = compute_percentiles(values, min_n=5)
        d = stats.to_dict()
        assert isinstance(d, dict)
        assert set(d.keys()) == {"p10", "p90", "mean", "n"}
        assert isinstance(d["p10"], float)
        assert isinstance(d["p90"], float)
        assert isinstance(d["mean"], float)
        assert isinstance(d["n"], int)

    def test_to_dict_none_stats(self):
        """to_dict with insufficient data returns None values."""
        stats = compute_percentiles([1.0, 2.0])
        d = stats.to_dict()
        assert d["p10"] is None
        assert d["p90"] is None
        assert d["mean"] is None
        assert d["n"] == 2
