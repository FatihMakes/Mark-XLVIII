"""
Role-registry / role-agent / handoff tests (stdlib unittest — no Gemini, no Qt).

Run:
    python -m unittest tests.core.test_roles -v

Covers the orchestration verification points for the role layer:
    Tier 1 — routing: obvious requests route; ambiguous ones return None (ask, don't guess)
    Tier 2 — bounded loop: a model that always asks for tools stops at max_iterations
    Tier 5 — handoff: an agent PROPOSES the next step; nothing dispatches without a yes
"""

import json
import tempfile
import unittest
from pathlib import Path

from core.manifest import AgentManifest, ManifestStore
from core.roles import RoleRegistry
from core.handoff import HandoffRecommendation, HandoffStore
from core.role_agent import RoleAgent, ModelTurn, ToolCall


ROOT = Path(__file__).resolve().parent.parent.parent


def _store_with(agents):
    d = tempfile.mkdtemp()
    path = Path(d) / "agents.json"
    path.write_text(json.dumps({"agents": agents}), encoding="utf-8")
    store = ManifestStore(path)
    store.load()
    return store


# --------------------------------------------------------------------------- #
# Tier 1 — routing
# --------------------------------------------------------------------------- #
class TestRoleRouting(unittest.TestCase):
    def setUp(self):
        self.reg = RoleRegistry(
            _store_with(
                [
                    {"name": "jarvis", "tools": ["*"]},
                    {"name": "eva", "dispatchable": True, "role": "gold desk",
                     "keywords": ["gold", "price"]},
                    {"name": "bobby", "dispatchable": True, "role": "news desk",
                     "keywords": ["news", "headline"]},
                    {"name": "tom", "dispatchable": True, "role": "trade desk",
                     "keywords": ["buy", "sell"], "requires_confirmation": True},
                ]
            )
        )

    def test_orchestrator_is_not_a_role(self):
        self.assertEqual(self.reg.names(), ["bobby", "eva", "tom"])
        self.assertIsNone(self.reg.get("jarvis"))

    def test_obvious_routes(self):
        self.assertEqual(self.reg.route("what's the gold price today"), "eva")
        self.assertEqual(self.reg.route("any market news this morning"), "bobby")
        self.assertEqual(self.reg.route("buy 2 ounces"), "tom")

    def test_ambiguous_returns_none(self):
        # mentions both news and buy -> ambiguous -> ask, don't guess
        self.assertIsNone(self.reg.route("show me the news then buy gold"))
        self.assertIsNone(self.reg.route("hello there"))

    def test_routing_policy_lists_roles_and_gate(self):
        policy = self.reg.routing_policy()
        self.assertIn("eva", policy)
        self.assertIn("bobby", policy)
        self.assertIn("tom", policy)
        self.assertIn("money move", policy)  # tom's gate is surfaced
        self.assertIn("dispatch_to_role", policy)

    def test_dispatch_tool_lists_roles(self):
        decl = self.reg.dispatch_tool_declaration()
        self.assertEqual(decl["name"], "dispatch_to_role")
        self.assertIn("eva", decl["parameters"]["properties"]["role"]["description"])


# --------------------------------------------------------------------------- #
# Tier 2 — bounded generic runtime
# --------------------------------------------------------------------------- #
class TestRoleAgentBounded(unittest.TestCase):
    def _agent(self, manifest, model_fn, dispatched=None):
        def dispatch_fn(name, args):
            if dispatched is not None:
                dispatched.append((name, args))
            return f"ran {name}"
        return RoleAgent(manifest, tool_declarations=[{"name": "web_search"}],
                         dispatch_fn=dispatch_fn, model_fn=model_fn)

    def test_runaway_loop_stops_at_cap(self):
        m = AgentManifest(name="eva", max_iterations=3)
        # model that ALWAYS asks for a tool -> never finishes
        model_fn = lambda mani, msgs, tools: ModelTurn(
            tool_calls=(ToolCall("web_search", {"q": "x"}),)
        )
        calls = []
        result = self._agent(m, model_fn, calls).run("loop forever")
        self.assertFalse(result.converged)
        self.assertEqual(result.iterations, 3)
        self.assertEqual(len(calls), 3)  # exactly cap dispatches, then stop
        self.assertIn("did not converge", result.result)

    def test_final_answer_converges(self):
        m = AgentManifest(name="eva", max_iterations=5)
        model_fn = lambda mani, msgs, tools: ModelTurn(text="Gold is $2400/oz.")
        result = self._agent(m, model_fn).run("gold price?")
        self.assertTrue(result.converged)
        self.assertEqual(result.result, "Gold is $2400/oz.")
        self.assertEqual(result.iterations, 1)

    def test_tool_then_answer(self):
        m = AgentManifest(name="eva", max_iterations=5)
        turns = iter([
            ModelTurn(tool_calls=(ToolCall("web_search", {"q": "gold"}),)),
            ModelTurn(text="Gold is $2400."),
        ])
        model_fn = lambda mani, msgs, tools: next(turns)
        calls = []
        result = self._agent(m, model_fn, calls).run("gold?")
        self.assertTrue(result.converged)
        self.assertEqual(calls, [("web_search", {"q": "gold"})])
        self.assertEqual(result.iterations, 2)

    def test_handoff_tool_is_offered(self):
        m = AgentManifest(name="eva")
        agent = self._agent(m, lambda *a: ModelTurn(text="done"))
        names = {t["name"] for t in agent.tool_declarations}
        self.assertIn("propose_handoff", names)
        self.assertIn("web_search", names)


# --------------------------------------------------------------------------- #
# Tier 5 — handoff: propose, don't chain
# --------------------------------------------------------------------------- #
class TestHandoff(unittest.TestCase):
    def test_agent_proposes_handoff_and_stops(self):
        m = AgentManifest(name="bobby", max_iterations=5)
        dispatched = []
        turns = iter([
            ModelTurn(tool_calls=(ToolCall("propose_handoff", {
                "target_role": "tom",
                "reason": "the headline implies you want to act",
                "task": "buy gold",
                "confidence": 0.8,
                "artifacts": {"article": "https://example.com/x"},
            }),)),
        ])
        agent = RoleAgent(
            m, tool_declarations=[{"name": "web_search"}],
            dispatch_fn=lambda n, a: dispatched.append((n, a)) or "x",
            model_fn=lambda *a: next(turns),
        )
        result = agent.run("any news?")
        self.assertIsNotNone(result.handoff)
        self.assertEqual(result.handoff.target_role, "tom")
        self.assertEqual(result.handoff.task, "buy gold")
        # Crucially: proposing did NOT dispatch tom (no chaining).
        self.assertEqual(dispatched, [])

    def test_handoff_store_requires_explicit_accept(self):
        store = HandoffStore()
        reco = HandoffRecommendation(target_role="tom", reason="r", task="buy gold",
                                     confidence=0.9)
        ph = store.propose(reco, source_role="bobby")
        payload = store.payload(ph)
        self.assertTrue(payload["handoff_proposed"])
        self.assertIn("tom", payload["offer"])
        # nothing dispatches until accept; accept yields the reco exactly once
        accepted = store.accept(ph.token)
        self.assertEqual(accepted.reco.task, "buy gold")
        self.assertIsNone(store.accept(ph.token))

    def test_reject_drops_handoff(self):
        store = HandoffStore()
        ph = store.propose(HandoffRecommendation(target_role="tom", reason="r", task="t"))
        self.assertTrue(store.reject(ph.token))
        self.assertIsNone(store.accept(ph.token))

    def test_malformed_recommendation_is_none(self):
        self.assertIsNone(HandoffRecommendation.from_dict(None))
        self.assertIsNone(HandoffRecommendation.from_dict({}))
        self.assertIsNone(HandoffRecommendation.from_dict({"target_role": "tom"}))  # no task
        self.assertIsNone(HandoffRecommendation.from_dict({"task": "buy"}))         # no target

    def test_offer_phrasing_scales_with_confidence(self):
        high = HandoffRecommendation(target_role="tom", reason="r", task="t", confidence=0.9)
        low = HandoffRecommendation(target_role="tom", reason="r", task="t", confidence=0.2)
        self.assertIn("strongly", high.offer_text())
        self.assertNotIn("strongly", low.offer_text())


# --------------------------------------------------------------------------- #
# Integration — the real agents.json wires Eva/Bobby/Tom correctly
# --------------------------------------------------------------------------- #
class TestRealRoles(unittest.TestCase):
    def setUp(self):
        store = ManifestStore(ROOT / "config" / "agents.json")
        store.load()
        self.reg = RoleRegistry(store)

    def test_three_named_roles_present(self):
        self.assertEqual(self.reg.names(), ["bobby", "eva", "tom"])

    def test_example_routes_from_user(self):
        # The exact routing the user described.
        self.assertEqual(self.reg.route("what is the gold price"), "eva")
        self.assertEqual(self.reg.route("give me the market news"), "bobby")
        self.assertEqual(self.reg.route("sell my position"), "tom")

    def test_tom_is_confirmation_gated(self):
        tom = self.reg.get("tom")
        self.assertTrue(tom.requires_confirmation)
        eva = self.reg.get("eva")
        self.assertFalse(eva.requires_confirmation)


if __name__ == "__main__":
    unittest.main(verbosity=2)
