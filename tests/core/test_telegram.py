"""
Telegram adapter tests (stdlib unittest — mocked HTTP, no network).

Run:
    python -m unittest tests.core.test_telegram -v

Covers:
  - send_message returns ok/error dict (never raises)
  - missing config returns a clear error
  - send_alert_tool entry point
"""

import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from core import telegram as TG


class FakeResponse:
    def __init__(self, data, status=200):
        self._data = data
        self.status_code = status

    def json(self):
        return self._data


class TestSendMessage(unittest.TestCase):

    def test_missing_config_returns_error(self):
        result = TG.send_message("hello", bot_token="", chat_id="")
        self.assertFalse(result["ok"])
        self.assertIn("not configured", result["error"])

    @mock.patch("core.telegram.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = FakeResponse({"ok": True, "result": {"message_id": 42}})
        result = TG.send_message("hello", bot_token="123:ABC", chat_id="999")
        self.assertTrue(result["ok"])
        self.assertEqual(result["message_id"], 42)
        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        self.assertIn("bot123:ABC", url)

    @mock.patch("core.telegram.requests.post")
    def test_api_error(self, mock_post):
        mock_post.return_value = FakeResponse({"ok": False, "description": "chat not found"})
        result = TG.send_message("hello", bot_token="123:ABC", chat_id="999")
        self.assertFalse(result["ok"])
        self.assertIn("chat not found", result["error"])

    @mock.patch("core.telegram.requests.post", side_effect=ConnectionError("offline"))
    def test_network_error_returns_error_data(self, _):
        result = TG.send_message("hello", bot_token="123:ABC", chat_id="999")
        self.assertFalse(result["ok"])
        self.assertIn("offline", result["error"])


class TestAlertTool(unittest.TestCase):

    @mock.patch("core.telegram.send_message", return_value={"ok": True, "message_id": 1})
    def test_tool_sends_message(self, mock_send):
        out = TG.send_alert_tool({"message": "Gold alert!"})
        self.assertIn("Alert sent", out)
        mock_send.assert_called_once()

    def test_empty_message_returns_error(self):
        out = TG.send_alert_tool({})
        self.assertIn("No message", out)

    @mock.patch("core.telegram.send_message", return_value={"ok": False, "error": "no token"})
    def test_tool_reports_failure(self, _):
        out = TG.send_alert_tool({"message": "test"})
        self.assertIn("failed", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
