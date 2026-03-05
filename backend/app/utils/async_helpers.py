"""
Centralized async thread helper for wrapping synchronous SDK calls.

All Bybit client modules use this instead of defining their own
_thread_with_timeout / _t helper.
"""
import asyncio

# Default timeout for SDK calls (seconds)
SDK_TIMEOUT = 10.0


async def thread_with_timeout(fn, *args, timeout: float = SDK_TIMEOUT, **kwargs):
    """Run a synchronous function in a thread with timeout protection.

    Uses asyncio.to_thread() for the thread pool and asyncio.wait_for()
    to enforce the timeout. If the function doesn't return within
    `timeout` seconds, asyncio.TimeoutError is raised.

    Args:
        fn: Synchronous callable to run in a thread.
        *args: Positional arguments forwarded to fn.
        timeout: Maximum wait time in seconds (default: 10.0).
        **kwargs: Keyword arguments forwarded to fn.

    Returns:
        The return value of fn(*args, **kwargs).

    Raises:
        asyncio.TimeoutError: If fn doesn't complete within timeout.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(fn, *args, **kwargs),
        timeout=timeout,
    )
