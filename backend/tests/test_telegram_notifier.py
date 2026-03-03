# file: backend/tests/test_telegram_notifier.py
"""
Tests for telegram_notifier.
Mocks aiohttp to avoid real network calls.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


from app.alerts.telegram_notifier import send_telegram


@pytest.mark.asyncio
class TestSendTelegram:

    @patch("app.alerts.telegram_notifier.settings")
    async def test_disabled_returns_false(self, mock_settings):
        mock_settings.telegram_enabled = False
        result = await send_telegram("hello")
        assert result is False

    @patch("app.alerts.telegram_notifier.settings")
    async def test_missing_token_returns_false(self, mock_settings):
        mock_settings.telegram_enabled = True
        mock_settings.telegram_bot_token = ""
        mock_settings.telegram_chat_id = "123"
        result = await send_telegram("hello")
        assert result is False

    @patch("app.alerts.telegram_notifier.settings")
    async def test_missing_chat_id_returns_false(self, mock_settings):
        mock_settings.telegram_enabled = True
        mock_settings.telegram_bot_token = "tok123"
        mock_settings.telegram_chat_id = ""
        result = await send_telegram("hello")
        assert result is False

    @patch("app.alerts.telegram_notifier._get_session")
    @patch("app.alerts.telegram_notifier.settings")
    async def test_success_returns_true(self, mock_settings, mock_get_session):
        mock_settings.telegram_enabled = True
        mock_settings.telegram_bot_token = "tok123"
        mock_settings.telegram_chat_id = "456"

        # Build a mock response context manager
        mock_resp = MagicMock()
        mock_resp.status = 200

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_get_session.return_value = mock_session

        result = await send_telegram("test message")
        assert result is True
        mock_session.post.assert_called_once()

    @patch("app.alerts.telegram_notifier._get_session")
    @patch("app.alerts.telegram_notifier.settings")
    async def test_api_error_retries_and_returns_false(self, mock_settings, mock_get_session):
        mock_settings.telegram_enabled = True
        mock_settings.telegram_bot_token = "tok123"
        mock_settings.telegram_chat_id = "456"

        # Return 500 every time
        mock_resp = MagicMock()
        mock_resp.status = 500
        mock_resp.text = AsyncMock(return_value="Internal Server Error")

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=mock_ctx)

        mock_get_session.return_value = mock_session

        # Patch sleep to avoid real delays
        with patch("app.alerts.telegram_notifier.asyncio.sleep", new_callable=AsyncMock):
            result = await send_telegram("test message")

        assert result is False
        assert mock_session.post.call_count == 3  # 3 retries
