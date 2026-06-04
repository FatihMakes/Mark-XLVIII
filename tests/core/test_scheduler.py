"""
Scheduler (gold watcher daemon) tests (stdlib unittest — fake TradingView, no network).

Run:
    python -m unittest tests.core.test_scheduler -v

Covers:
  - tick records a heartbeat decision in audit
  - price-move alert fires when threshold exceeded
  - small moves do NOT alert
  - failed analysis logged as error
  - start/stop lifecycle
"""

import unittest
from unittest import mock

from core.audit import AuditLog
from core.scheduler import GoldWatcher


def _fake_analysis(price=4450.0, rec="NEUTRAL"):
    return {
        "ok": True, "text": f"XAUUSD (15m): {price}. Signal: {rec}.",
        "symbol": "XAUUSD", "close": price, "recommendation": rec,
    }


class TestTick(unittest.TestCase):
    def setUp(self):
        self.audit = AuditLog(":memory:")

    def tearDown(self):
        self.audit.close()

    @mock.patch("core.scheduler.get_analysis", return_value=_fake_analysis(4450.0))
    @mock.patch("core.scheduler.send_message")
    def test_heartbeat_logged(self, mock_tg, mock_tv):
        w = GoldWatcher(self.audit, interval_seconds=9999)
        w._tick()
        decisions = self.audit.recent_decisions()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["actor"], "daemon")
        self.assertEqual(decisions[0]["action"], "gold_check")
        self.assertIn("4450", decisions[0]["task"])

    @mock.patch("core.scheduler.get_analysis", return_value=_fake_analysis(4500.0))
    @mock.patch("core.scheduler.send_message", return_value={"ok": True, "message_id": 1})
    def test_big_move_triggers_alert(self, mock_tg, mock_tv):
        w = GoldWatcher(self.audit, interval_seconds=9999, alert_threshold_pct=0.3)
        w._last_price = 4400.0  # simulate previous check
        w._tick()
        # 4400 -> 4500 = 2.27% move, well above 0.3% threshold
        mock_tg.assert_called_once()
        alert_text = mock_tg.call_args[0][0]
        self.assertIn("UP", alert_text)
        self.assertIn("Gold Alert", alert_text)

    @mock.patch("core.scheduler.get_analysis", return_value=_fake_analysis(4451.0))
    @mock.patch("core.scheduler.send_message")
    def test_small_move_no_alert(self, mock_tg, mock_tv):
        w = GoldWatcher(self.audit, interval_seconds=9999, alert_threshold_pct=0.3)
        w._last_price = 4450.0  # 0.02% move
        w._tick()
        mock_tg.assert_not_called()

    @mock.patch("core.scheduler.get_analysis", return_value={"ok": False, "text": "network down"})
    def test_failed_analysis_logged(self, _):
        w = GoldWatcher(self.audit, interval_seconds=9999)
        w._tick()
        d = self.audit.recent_decisions()[0]
        self.assertEqual(d["status"], "failed")
        self.assertIn("network down", d["error"] or "")


class TestLifecycle(unittest.TestCase):
    def test_start_stop(self):
        audit = AuditLog(":memory:")
        w = GoldWatcher(audit, interval_seconds=9999)
        self.assertFalse(w.running)
        w.start()
        self.assertTrue(w.running)
        w.stop()
        self.assertFalse(w.running)
        audit.close()

    def test_status(self):
        audit = AuditLog(":memory:")
        w = GoldWatcher(audit, interval_seconds=600, alert_threshold_pct=0.5)
        s = w.status()
        self.assertEqual(s["interval"], 600)
        self.assertEqual(s["threshold"], 0.5)
        self.assertFalse(s["running"])
        audit.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
