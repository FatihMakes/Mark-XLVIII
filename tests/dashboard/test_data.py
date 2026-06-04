"""
Dashboard data-layer tests (stdlib unittest — no Streamlit, no browser).

Run:
    python -m unittest tests.dashboard.test_data -v

Verifies the read-only derivations the dashboard renders:
  - the roster lists every agent with the orchestrator first
  - each agent's live "pulse" is derived from its latest decision (working/idle/gated)
  - pending handoffs = proposed-but-not-resolved
  - empty DB degrades to an all-idle roster (Jarvis not started yet)
"""

import time
import unittest
from pathlib import Path

from core.audit import AuditLog
from core.manifest import ManifestStore
from dashboard import data as D


ROOT = Path(__file__).resolve().parent.parent.parent


def _store():
    s = ManifestStore(ROOT / "config" / "agents.json")
    s.load()
    return s


class TestRoster(unittest.TestCase):
    def test_orchestrator_first_then_roles(self):
        cards = D.agent_roster(_store())
        names = [c["name"] for c in cards]
        self.assertEqual(names[0], "jarvis")
        self.assertIn("eva", names)
        self.assertIn("tom", names)

    def test_tom_marked_gated(self):
        cards = {c["name"]: c for c in D.agent_roster(_store())}
        self.assertTrue(cards["tom"]["gated"])
        self.assertFalse(cards["eva"]["gated"])


class TestPulse(unittest.TestCase):
    def setUp(self):
        self.audit = AuditLog(":memory:")

    def tearDown(self):
        self.audit.close()

    def test_idle_when_no_history(self):
        status = D.agent_status(self.audit, ["eva", "tom"])
        self.assertEqual(status["eva"]["status"], "idle")
        self.assertIsNone(status["eva"]["last_ts"])

    def test_working_when_recent_pending(self):
        self.audit.record_decision("jarvis", "dispatch", target_role="eva",
                                   task="gold price", status="pending")
        status = D.agent_status(self.audit, ["eva"])
        self.assertEqual(status["eva"]["status"], "working")
        self.assertEqual(status["eva"]["last_task"], "gold price")

    def test_awaiting_confirmation_when_blocked(self):
        self.audit.record_decision("jarvis", "gate", target_role="tom",
                                   task="buy gold", status="blocked")
        status = D.agent_status(self.audit, ["tom"])
        self.assertEqual(status["tom"]["status"], "awaiting confirmation")

    def test_idle_when_executed(self):
        self.audit.record_decision("jarvis", "dispatch", target_role="eva",
                                   task="gold", status="executed")
        status = D.agent_status(self.audit, ["eva"])
        self.assertEqual(status["eva"]["status"], "idle")

    def test_latest_decision_wins(self):
        self.audit.record_decision("jarvis", "dispatch", target_role="eva",
                                   task="old", status="executed")
        time.sleep(0.01)
        self.audit.record_decision("jarvis", "dispatch", target_role="eva",
                                   task="new", status="pending")
        status = D.agent_status(self.audit, ["eva"])
        self.assertEqual(status["eva"]["last_task"], "new")
        self.assertEqual(status["eva"]["status"], "working")


class TestOverviewAndHandoffs(unittest.TestCase):
    def setUp(self):
        self.audit = AuditLog(":memory:")

    def tearDown(self):
        self.audit.close()

    def test_overview_merges_roster_and_pulse(self):
        self.audit.record_decision("jarvis", "dispatch", target_role="eva",
                                   task="gold", status="pending")
        cards = D.overview(self.audit, _store())
        eva = next(c for c in cards if c["name"] == "eva")
        self.assertEqual(eva["status"], "working")
        self.assertEqual(eva["role"], "gold & numbers desk")

    def test_pending_handoffs_only_unresolved(self):
        self.audit.record_handoff("bobby", "tom", reason="r", token="t1")
        self.audit.record_handoff("eva", "tom", reason="r2", token="t2")
        self.audit.resolve_handoff("t2", accepted=True)
        pend = D.pending_handoffs(self.audit)
        tokens = {h["token"] for h in pend}
        self.assertEqual(tokens, {"t1"})

    def test_fmt_ts_handles_none(self):
        self.assertEqual(D.fmt_ts(None), "—")
        self.assertNotEqual(D.fmt_ts(time.time()), "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)
