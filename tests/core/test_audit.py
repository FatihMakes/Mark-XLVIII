"""
Audit-trail tests (stdlib unittest — in-memory SQLite, no app deps).

Run:
    python -m unittest tests.core.test_audit -v

Covers the black-box guarantees:
  - record-before-act: a decision logs as 'pending', then updates to executed/failed
  - tool calls and handoffs link to their decision and are queryable newest-first
  - the full lifecycle of a gated trade is reconstructable from the log
  - a logging failure never raises (it degrades quietly)
"""

import threading
import unittest

from core.audit import AuditLog, prompt_hash


class TestDecisions(unittest.TestCase):
    def setUp(self):
        self.log = AuditLog(":memory:")

    def tearDown(self):
        self.log.close()

    def test_record_then_update(self):
        did = self.log.record_decision(
            "jarvis", "dispatch", target_role="tom", task="buy 2oz gold",
            status="pending", system_prompt="You are Tom.")
        self.assertIsInstance(did, int)
        self.log.update_decision(did, status="executed", result="order described")
        row = self.log.recent_decisions()[0]
        self.assertEqual(row["actor"], "jarvis")
        self.assertEqual(row["target_role"], "tom")
        self.assertEqual(row["status"], "executed")
        self.assertEqual(row["result"], "order described")
        self.assertNotEqual(row["prompt_hash"], "")  # prompt fingerprinted

    def test_pending_default(self):
        did = self.log.record_decision("jarvis", "route", task="gold price")
        self.assertEqual(self.log.recent_decisions()[0]["status"], "pending")
        self.log.update_decision(did, status="failed", error="boom")
        self.assertEqual(self.log.recent_decisions()[0]["status"], "failed")

    def test_update_none_id_is_safe(self):
        self.log.update_decision(None, status="executed")  # must not raise


class TestToolCallsAndHandoffs(unittest.TestCase):
    def setUp(self):
        self.log = AuditLog(":memory:")

    def tearDown(self):
        self.log.close()

    def test_tool_call_linked_to_decision(self):
        did = self.log.record_decision("eva", "run", task="gold price")
        tid = self.log.record_tool_call(
            "web_search", decision_id=did, actor="eva",
            args={"query": "gold price"}, result="2412.50")
        self.assertIsInstance(tid, int)
        tc = self.log.recent_tool_calls()[0]
        self.assertEqual(tc["decision_id"], did)
        self.assertEqual(tc["tool"], "web_search")
        self.assertIn("gold", tc["args"])

    def test_handoff_lifecycle(self):
        self.log.record_handoff("bobby", "tom", reason="headline implies a trade",
                                token="abc123", confidence=0.8)
        h = self.log.recent_handoffs()[0]
        self.assertEqual(h["from_role"], "bobby")
        self.assertEqual(h["to_role"], "tom")
        self.assertIsNone(h["accepted"])  # pending
        self.log.resolve_handoff("abc123", accepted=True)
        self.assertEqual(self.log.recent_handoffs()[0]["accepted"], 1)


class TestReconstructTradeStory(unittest.TestCase):
    """The whole point: replay why a gated trade happened, end to end."""

    def test_full_gated_trade_is_reconstructable(self):
        log = AuditLog(":memory:")
        # 1) Bobby finds news and proposes a handoff to Tom
        d1 = log.record_decision("bobby", "run", task="any gold news")
        log.record_tool_call("web_search", decision_id=d1, actor="bobby",
                             args={"query": "gold news"}, result="Gold breaks out")
        log.update_decision(d1, status="executed")
        log.record_handoff("bobby", "tom", reason="breakout implies a buy",
                           token="t1", confidence=0.8)
        # 2) Human approves the handoff
        log.resolve_handoff("t1", accepted=True)
        # 3) Tom is gated, then confirmed, then "executes"
        d2 = log.record_decision("jarvis", "gate", target_role="tom",
                                 task="buy 2oz gold", status="blocked")
        log.update_decision(d2, status="approved")
        d3 = log.record_decision("tom", "execute", target_role="tom",
                                 task="buy 2oz gold", status="pending")
        log.update_decision(d3, status="executed", result="Would place BUY 2oz XAU")

        # Replay: a reviewer can see the whole chain
        decisions = log.recent_decisions()
        actions = {d["action"] for d in decisions}
        self.assertEqual(actions, {"run", "gate", "execute"})
        handoff = log.recent_handoffs()[0]
        self.assertEqual(handoff["accepted"], 1)
        st = log.stats()
        self.assertEqual(st["decisions"], 3)
        self.assertEqual(st["handoffs"], 1)
        self.assertEqual(st["by_actor"]["bobby"], 1)
        self.assertEqual(st["by_status"]["executed"], 2)
        log.close()


class TestRobustness(unittest.TestCase):
    def test_prompt_hash_stable_and_short(self):
        self.assertEqual(prompt_hash("abc"), prompt_hash("abc"))
        self.assertNotEqual(prompt_hash("abc"), prompt_hash("abd"))
        self.assertEqual(len(prompt_hash("abc")), 12)
        self.assertEqual(prompt_hash(""), "")

    def test_logging_after_close_does_not_raise(self):
        log = AuditLog(":memory:")
        log.close()
        # Writes after close must degrade quietly, never raise.
        self.assertIsNone(log.record_decision("jarvis", "route", task="x"))

    def test_concurrent_writes(self):
        log = AuditLog(":memory:")

        def worker(n):
            for i in range(20):
                log.record_decision("jarvis", "route", task=f"{n}-{i}")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(log.stats()["decisions"], 100)
        log.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
