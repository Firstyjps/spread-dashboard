"""
Percentile computation for spread time-series data.

Pure Python implementation (no numpy dependency).
Uses linear interpolation matching numpy.percentile(method='linear').
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


# Minimum sample size required for meaningful percentiles.
MIN_SAMPLE_SIZE = 20


@dataclass(frozen=True, slots=True)
class SpreadStats:
    """Percentile statistics for a spread window."""

    p10: Optional[float]
    p90: Optional[float]
    mean: Optional[float]
    n: int

    def to_dict(self) -> dict:
        return {
            "p10": round(self.p10, 4) if self.p10 is not None else None,
            "p90": round(self.p90, 4) if self.p90 is not None else None,
            "mean": round(self.mean, 4) if self.mean is not None else None,
            "n": self.n,
        }


def _linear_percentile(sorted_values: list[float], q: float) -> float:
    """
    Compute the q-th percentile of sorted_values using linear interpolation.

    Matches numpy.percentile(a, q, method='linear'):
      virtual_index = (n - 1) * q / 100
      lower = floor(virtual_index)
      fraction = virtual_index - lower
      result = sorted_values[lower] + fraction * (sorted_values[lower+1] - sorted_values[lower])

    Parameters
    ----------
    sorted_values : list[float]
        Pre-sorted (ascending) list of numeric values. Must have len >= 1.
    q : float
        Percentile in [0, 100].

    Returns
    -------
    float
        The interpolated percentile value.
    """
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]

    idx = (n - 1) * q / 100.0
    lo = int(math.floor(idx))
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


def compute_percentiles(
    values: Sequence[float | None],
    *,
    min_n: int = MIN_SAMPLE_SIZE,
) -> SpreadStats:
    """
    Compute P10/P90 spread statistics from a sequence of spread values.

    Parameters
    ----------
    values : Sequence[float | None]
        Raw spread values (may contain None / NaN). These should already
        be in the target unit (e.g., raw ratio — the frontend converts to bps).
    min_n : int
        Minimum number of valid samples required. If fewer, stats are None.

    Returns
    -------
    SpreadStats
        Dataclass with p10, p90, mean, n fields.
    """
    # Filter out None and NaN
    clean: list[float] = [
        v for v in values if v is not None and not math.isnan(v)
    ]

    n = len(clean)
    if n < min_n:
        return SpreadStats(p10=None, p90=None, mean=None, n=n)

    clean.sort()

    p10 = _linear_percentile(clean, 10)
    p90 = _linear_percentile(clean, 90)
    mean_val = sum(clean) / n

    return SpreadStats(p10=p10, p90=p90, mean=mean_val, n=n)
