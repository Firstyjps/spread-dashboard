"""Process-local kill switch for execution safety."""
import time


class CircuitBreaker:
    def __init__(self):
        self.tripped = False
        self.trip_reason: str = ""
        self.trip_ts: float = 0
        self.consecutive_failures: int = 0
        self.max_failures: int = 3
        self.feed_gap_threshold_s: float = 60.0

    def trip(self, reason: str) -> bool:
        """Trip the breaker. Returns True only when this is a new trip."""
        if self.tripped:
            return False
        self.tripped = True
        self.trip_reason = reason
        self.trip_ts = time.time() * 1000
        return True

    def reset(self):
        self.tripped = False
        self.trip_reason = ""
        self.trip_ts = 0
        self.consecutive_failures = 0

    def check_feed_staleness(self, last_tick_ts: float) -> bool:
        if not last_tick_ts:
            return False
        tick_ts_s = last_tick_ts / 1000 if last_tick_ts > 10_000_000_000 else last_tick_ts
        age_s = time.time() - tick_ts_s
        if age_s > self.feed_gap_threshold_s:
            return self.trip(f"feed stale for {age_s:.1f}s")
        return False

    def record_execution_failure(self) -> bool:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_failures:
            return self.trip(f"{self.consecutive_failures} consecutive execution failures")
        return False

    def record_execution_success(self):
        self.consecutive_failures = 0

    @property
    def is_tripped(self) -> bool:
        return self.tripped

    def status(self) -> dict:
        return {
            "tripped": self.tripped,
            "trip_reason": self.trip_reason,
            "trip_ts": self.trip_ts,
            "consecutive_failures": self.consecutive_failures,
            "max_failures": self.max_failures,
            "feed_gap_threshold_s": self.feed_gap_threshold_s,
        }


circuit_breaker = CircuitBreaker()
