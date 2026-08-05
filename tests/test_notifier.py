"""
Tests for TelegramNotifier (src/notifier.py).

The HTTP call to Telegram is mocked so tests run fully offline.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.notifier import TelegramNotifier
from src.models import Signal, SignalType


def _make_signal(sig_type=SignalType.LONG, is_hard=True):
    return Signal(
        timestamp=datetime(2026, 8, 5, 3, 45, 0),
        symbol="BTC/USDT:USDT",
        timeframe="15m",
        type=sig_type,
        price=60000.0,
        message="🔥 HARD LONG: Match (SAR Filter OK)",
        is_hard=is_hard,
    )


class TestTelegramNotifier:
    @pytest.fixture
    def notifier(self):
        return TelegramNotifier(token="fake_token", tz_offset=7)

    # ------------------------------------------------------------------
    # Message formatting
    # ------------------------------------------------------------------

    def test_send_signal_calls_post_for_each_chat_id(self, notifier):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()

        with patch("src.notifier.requests.post", return_value=mock_resp) as mock_post:
            notifier.send_signal(_make_signal(), chat_ids=[111, 222, 333])

        assert mock_post.call_count == 3

    def test_long_signal_uses_green_emoji(self, notifier):
        captured = []

        def fake_post(url, json, **kwargs):
            captured.append(json["text"])
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with patch("src.notifier.requests.post", side_effect=fake_post):
            notifier.send_signal(_make_signal(SignalType.LONG), chat_ids=[1])

        assert "🟢 LONG" in captured[0]

    def test_short_signal_uses_red_emoji(self, notifier):
        captured = []

        def fake_post(url, json, **kwargs):
            captured.append(json["text"])
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with patch("src.notifier.requests.post", side_effect=fake_post):
            notifier.send_signal(_make_signal(SignalType.SHORT), chat_ids=[1])

        assert "🔴 SHORT" in captured[0]

    def test_timezone_offset_applied_to_timestamp(self, notifier):
        """UTC 03:45 + 7h offset → 10:45 in message."""
        captured = []

        def fake_post(url, json, **kwargs):
            captured.append(json["text"])
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with patch("src.notifier.requests.post", side_effect=fake_post):
            notifier.send_signal(_make_signal(), chat_ids=[1])

        assert "10:45:00" in captured[0]
        assert "UTC+7" in captured[0]

    def test_strict_mode_shown_as_yes_for_hard(self, notifier):
        captured = []

        def fake_post(url, json, **kwargs):
            captured.append(json["text"])
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with patch("src.notifier.requests.post", side_effect=fake_post):
            notifier.send_signal(_make_signal(is_hard=True), chat_ids=[1])

        assert "Yes" in captured[0]

    def test_strict_mode_shown_as_no_for_sequential(self, notifier):
        captured = []

        def fake_post(url, json, **kwargs):
            captured.append(json["text"])
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with patch("src.notifier.requests.post", side_effect=fake_post):
            notifier.send_signal(_make_signal(is_hard=False), chat_ids=[1])

        assert "No" in captured[0]

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_http_error_does_not_raise(self, notifier):
        """A failed HTTP call must be swallowed gracefully (no crash)."""
        def bad_post(url, json, **kwargs):
            raise ConnectionError("timeout")

        with patch("src.notifier.requests.post", side_effect=bad_post):
            # Should not raise — errors are caught internally
            notifier.send_signal(_make_signal(), chat_ids=[1])

    def test_send_to_empty_chat_ids_does_nothing(self, notifier):
        with patch("src.notifier.requests.post") as mock_post:
            notifier.send_signal(_make_signal(), chat_ids=[])
        mock_post.assert_not_called()

    def test_negative_tz_offset_formats_correctly(self):
        notifier = TelegramNotifier(token="t", tz_offset=-5)
        captured = []

        def fake_post(url, json, **kwargs):
            captured.append(json["text"])
            r = MagicMock()
            r.raise_for_status = MagicMock()
            return r

        with patch("src.notifier.requests.post", side_effect=fake_post):
            notifier.send_signal(_make_signal(), chat_ids=[1])

        assert "UTC-5" in captured[0]
