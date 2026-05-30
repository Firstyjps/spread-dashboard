from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque


class OrderRateLimiter:
    def __init__(self, max_per_minute: int = 10, timeout_s: float = 30.0) -> None:
        self.max_per_minute = max_per_minute
        self.timeout_s = timeout_s
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._discard_event = asyncio.Event()

    def update_config(self, *, max_per_minute: int, timeout_s: float) -> None:
        self.max_per_minute = max_per_minute
        self.timeout_s = timeout_s

    async def acquire(self, exchange: str) -> bool:
        deadline = time.monotonic() + self.timeout_s
        exchange_key = exchange.lower()
        while True:
            if self._discard_event.is_set():
                return False

            async with self._lock:
                now = time.monotonic()
                self._prune(exchange_key, now)
                if len(self._events[exchange_key]) < self.max_per_minute:
                    self._events[exchange_key].append(now)
                    return True

                wait_s = max(0.01, 60.0 - (now - self._events[exchange_key][0]))

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            await asyncio.sleep(min(wait_s, remaining, 0.25))

    def discard_all(self) -> None:
        self._discard_event.set()
        for events in self._events.values():
            events.clear()
        self._discard_event.clear()

    def get_rate_status(self, exchange: str | None = None) -> dict[str, dict[str, float | int | bool]]:
        now = time.monotonic()
        exchanges = [exchange.lower()] if exchange else list(self._events.keys())
        status: dict[str, dict[str, float | int | bool]] = {}
        for key in exchanges:
            self._prune(key, now)
            used = len(self._events[key])
            status[key] = {
                "used": used,
                "remaining": max(0, self.max_per_minute - used),
                "limit": self.max_per_minute,
                "window_s": 60,
                "queued": used >= self.max_per_minute,
            }
        return status

    def _prune(self, exchange: str, now: float) -> None:
        events = self._events[exchange]
        while events and now - events[0] >= 60.0:
            events.popleft()
