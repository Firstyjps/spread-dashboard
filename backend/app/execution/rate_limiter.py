"""
Async token-bucket rate limiter for Bybit V5 API.

Bybit linear perps: 10 req/s for order endpoints, 20 req/s for query.
Single bucket for order operations (place/amend/cancel/query).
Shared across all execution strategies.
"""
import asyncio
import time
import structlog
from dataclasses import dataclass

log = structlog.get_logger()


@dataclass
class RateLimiterConfig:
    max_tokens: int = 10          # bucket capacity
    refill_rate: float = 10.0     # tokens per second
    retry_wait_s: float = 0.1     # sleep granularity when waiting


class TokenBucketRateLimiter:
    """
    Async token bucket.

    Usage:
        limiter = TokenBucketRateLimiter(RateLimiterConfig())
        async with limiter:   # acquires 1 token, waits if empty
            await client.place_order(...)

    Or explicitly:
        await limiter.acquire()
        await limiter.acquire(tokens=2)
    """

    def __init__(self, config: RateLimiterConfig | None = None):
        cfg = config or RateLimiterConfig()
        self._max_tokens: int = cfg.max_tokens
        self._refill_rate: float = cfg.refill_rate
        self._retry_wait: float = cfg.retry_wait_s
        self._tokens: float = float(cfg.max_tokens)
        self._last_refill: float = time.monotonic()
        self._lock: asyncio.Lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._max_tokens,
            self._tokens + elapsed * self._refill_rate,
        )
        self._last_refill = now

    async def acquire(self, tokens: int = 1) -> None:
        """Block until `tokens` are available, then consume them."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
            # Outside lock — sleep and retry
            await asyncio.sleep(self._retry_wait)

    async def __aenter__(self):
        await self.acquire(1)
        return self

    async def __aexit__(self, *exc):
        pass

    @property
    def available(self) -> float:
        """Current token count (non-blocking peek)."""
        self._refill()
        return self._tokens
