# file: backend/app/alerts/telegram_notifier.py
"""
Telegram Bot API notifier.
Persistent aiohttp session, 3 retries with exponential backoff + jitter.
Never raises — logs warning and returns False on failure.
"""
import asyncio
import random
from typing import Optional

import aiohttp
import structlog

from app.config import settings

log = structlog.get_logger()

_TELEGRAM_API = "https://api.telegram.org"
_TIMEOUT = aiohttp.ClientTimeout(total=5)
_MAX_RETRIES = 3

# Persistent session (lazy-init, same pattern as lighter_collector.py)
_session: Optional[aiohttp.ClientSession] = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=_TIMEOUT,
            connector=aiohttp.TCPConnector(limit=5, ttl_dns_cache=300),
        )
    return _session


async def close_session() -> None:
    """Close the persistent aiohttp session. Called on app shutdown."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def send_telegram(text: str) -> bool:
    """
    Send a message via Telegram Bot API.

    Returns True on success, False on failure.
    Never raises — logs warning and returns False.

    Retry strategy: 3 attempts, exponential backoff (1s, 2s, 4s) + random jitter.
    """
    if not settings.telegram_enabled:
        return False
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        log.warning("telegram_not_configured")
        return False

    url = f"{_TELEGRAM_API}/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    for attempt in range(_MAX_RETRIES):
        try:
            session = await _get_session()
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    log.debug("telegram_sent", chars=len(text))
                    return True
                body = await resp.text()
                log.warning(
                    "telegram_api_error",
                    status=resp.status,
                    body=body[:200],
                    attempt=attempt + 1,
                )
        except Exception as e:
            log.warning(
                "telegram_send_error",
                error=str(e),
                attempt=attempt + 1,
            )

        # Backoff before next retry (skip after last attempt)
        if attempt < _MAX_RETRIES - 1:
            backoff = (2 ** attempt) + random.uniform(0, 1)
            await asyncio.sleep(backoff)

    log.error("telegram_send_failed_all_retries", text_preview=text[:80])
    return False
