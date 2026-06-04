"""
Orchestration-layer tests (stdlib unittest — no pytest, no Gemini, no Qt required).

Run from the project root:
    python -m unittest tests.core.test_orchestration -v

These cover the verification checklists from the orchestration spec:
    Tier 2  — least-privilege allowlist + the registry as one source of truth
    Tier 3  — failure isolation: a throwing tool comes back as data, not a crash
    Tier 4  — confirmation gate: a gated tool stages instead of running, then runs once
    Tier 6  — hot-reload: add/remove a manifest and the dispatch tools follow
"""

import json
import tempfile
import unittest
from pathlib import Path

from core.registry import ToolRegistry, ToolSpec, ToolError
from core.confirmation import ConfirmationStore
from core.manifest import (
    AgentManifest,
    ManifestStore,
    make_dispatch_tool,
    DEFAULT_MAX_ITERATIONS,
)


def _schema(name: str) -> dict:
    return {
        "name": name,
        "description": f"test tool {name}",
        "parameters": {"type": "OBJECT", "properties": {}},
    }


# --------------------------------------------------------------------------- #
# Tier 2 — registry + least-privilege scoping
# --------------------------------------------------------------------------- #
class TestRegistryScoping(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()
        self.reg.register_schemas([_schema("web_search"), _schema("send_message")])
        self.reg.apply_metadata(
            {
                "web_search": {"agents": ["jarvis", "task"]},
                "send_message": {"agents": ["jarvis"], "requires_confirmation": True},
            }
        )

    def test_allowlist_filters_declarations(self):
        # The task agent gets a 1-tool view, not the whole set.
        task_decls = self.reg.declarations(agent="task")
        names = [d["name"] for d in task_decls]
        self.assertEqual(names, ["web_search"])

        # The unscoped orchestrator sees everything.
        all_names = [d["name"] for d in self.reg.declarations(agent=None)]
        self.assertEqual(all_names, ["send_message", "web_search"])

    def test_jarvis_sees_both(self):
        names = [d["name"] for d in self.reg.declarations(agent="jarvis")]
        self.assertEqual(names, ["send_message", "web_search"])

    def test_dispatch_blocked_for_disallowed_agent(self):
        self.reg.bind("send_message", lambda args, ctx: "sent")
        with self.assertRaises(ToolError):
            self.reg.dispatch("send_message", {}, ctx=None, agent="task")

    def test_confirmation_metadata_round_trips(self):
        self.assertTrue(self.reg.requires_confirmation("send_message"))
        self.assertFalse(self.reg.requires_confirmation("web_search"))

    def test_unknown_metadata_is_ignored(self):
        # Config can reference a not-yet-built tool without blowing up.
        self.reg.apply_metadata({"future_tool": {"requires_confirmation": True}})
        self.assertFalse(self.reg.has("future_tool"))


# --------------------------------------------------------------------------- #
# Tier 3 — failure isolation
# --------------------------------------------------------------------------- #
class TestFailureIsolation(unittest.TestCase):
    def setUp(self):
        self.reg = ToolRegistry()
        self.reg.register_schema(_schema("boom"))

    def test_throwing_handler_returns_error_as_data(self):
        def boom(args, ctx):
            raise RuntimeError("kaboom")

        self.reg.bind("boom", boom)
        result = self.reg.dispatch("boom", {}, ctx=None)
        self.assertIsInstance(result, str)
        self.assertIn("boom", result)
        self.assertIn("kaboom", result)

    def test_unbound_handler_raises_registry_error(self):
        with self.assertRaises(ToolError):
            self.reg.dispatch("boom", {}, ctx=None)


# --------------------------------------------------------------------------- #
# Tier 4 — confirmation gate
# --------------------------------------------------------------------------- #
class TestConfirmationGate(unittest.TestCase):
    def setUp(self):
        self.store = ConfirmationStore()

    def test_stage_returns_token_and_payload(self):
        action = self.store.stage("send_message", {"receiver": "John", "text": "hi"})
        payload = self.store.confirmation_payload(action)
        self.assertTrue(payload["confirmation_required"])
        self.assertEqual(payload["token"], action.token)
        self.assertIn("John", payload["summary"])

    def test_approve_returns_action_once(self):
        action = self.store.stage("shutdown_jarvis", {})
        approved = self.store.approve(action.token)
        self.assertIsNotNone(approved)
        self.assertEqual(approved.tool, "shutdown_jarvis")
        # Second approve must NOT replay the action.
        self.assertIsNone(self.store.approve(action.token))

    def test_reject_drops_pending(self):
        action = self.store.stage("send_message", {"receiver": "X"})
        self.assertTrue(self.store.reject(action.token))
        self.assertIsNone(self.store.approve(action.token))
        self.assertEqual(self.store.pending(), [])

    def test_unknown_token_is_safe(self):
        self.assertIsNone(self.store.approve("deadbeef"))
        self.assertFalse(self.store.reject("deadbeef"))

    def test_ttl_eviction(self):
        import time

        store = ConfirmationStore(ttl_seconds=0.05)  # expires almost immediately
        action = store.stage("send_message", {})
        time.sleep(0.1)
        self.assertIsNone(store.approve(action.token))

    def test_ttl_zero_means_never_expire(self):
        store = ConfirmationStore(ttl_seconds=0)  # 0 disables expiry
        action = store.stage("send_message", {})
        self.assertIsNotNone(store.approve(action.token))


# --------------------------------------------------------------------------- #
# Tier 2/6 — manifests, allowlist resolution, hot-reload
# --------------------------------------------------------------------------- #
class TestManifests(unittest.TestCase):
    def test_wildcard_allows_all_known(self):
        m = AgentManifest(name="jarvis", tools=("*",))
        self.assertTrue(m.allows_all_tools())
        self.assertEqual(
            m.allowed_tools(["a", "b"]),
            ["a", "b"],
        )
        self.assertTrue(m.may_use("anything"))

    def test_explicit_allowlist(self):
        m = AgentManifest(name="task", tools=("web_search", "file_controller"))
        self.assertTrue(m.may_use("web_search"))
        self.assertFalse(m.may_use("send_message"))
        # Resolving against known tools drops unknowns.
        self.assertEqual(
            m.allowed_tools(["web_search", "send_message"]),
            ["web_search"],
        )

    def test_default_iteration_cap(self):
        m = AgentManifest(name="x")
        self.assertEqual(m.max_iterations, DEFAULT_MAX_ITERATIONS)

    def test_make_dispatch_tool(self):
        m = AgentManifest(name="research", description="Deep research agent.")
        tool = make_dispatch_tool(m)
        self.assertEqual(tool["name"], "dispatch_to_research")
        self.assertIn("task", tool["parameters"]["properties"])


class TestHotReload(unittest.TestCase):
    def _write(self, path, agents):
        path.write_text(json.dumps({"agents": agents}), encoding="utf-8")

    def test_add_and_remove_agent_at_runtime(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "agents.json"
            self._write(path, [{"name": "jarvis", "tools": ["*"]}])

            store = ManifestStore(path)
            store.load()
            self.assertEqual(sorted(store.agents()), ["jarvis"])

            previous = store.agents()

            # Add a new agent + retire by writing a fresh roster.
            self._write(
                path,
                [
                    {"name": "jarvis", "tools": ["*"]},
                    {"name": "research", "tools": ["web_search"]},
                ],
            )
            self.assertTrue(store.reload_if_changed())
            added, removed = store.diff(previous)
            self.assertEqual(added, ["research"])
            self.assertEqual(removed, [])

            # Deactivating drops it from the live roster.
            previous = store.agents()
            self._write(
                path,
                [
                    {"name": "jarvis", "tools": ["*"]},
                    {"name": "research", "tools": ["web_search"], "active": False},
                ],
            )
            self.assertTrue(store.reload_if_changed())
            _, removed = store.diff(previous)
            self.assertEqual(removed, ["research"])

    def test_reload_noop_when_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "agents.json"
            self._write(path, [{"name": "jarvis", "tools": ["*"]}])
            store = ManifestStore(path)
            store.load()
            self.assertFalse(store.reload_if_changed())


# --------------------------------------------------------------------------- #
# Integration — the real config files parse and scope correctly
# --------------------------------------------------------------------------- #
class TestRealConfig(unittest.TestCase):
    ROOT = Path(__file__).resolve().parent.parent.parent

    def test_agents_json_parses(self):
        store = ManifestStore(self.ROOT / "config" / "agents.json")
        agents = store.load()
        self.assertIn("jarvis", agents)
        self.assertIn("task", agents)

    def test_task_agent_cannot_message_or_shutdown(self):
        store = ManifestStore(self.ROOT / "config" / "agents.json")
        agents = store.load()
        task = agents["task"]
        # The whole point of scoping the autonomous agent:
        self.assertFalse(task.may_use("send_message"))
        self.assertFalse(task.may_use("shutdown_jarvis"))
        self.assertFalse(task.may_use("game_updater"))
        self.assertTrue(task.may_use("web_search"))

    def test_tools_json_marks_risky_tools_for_confirmation(self):
        meta = json.loads(
            (self.ROOT / "config" / "tools.json").read_text(encoding="utf-8")
        )
        self.assertTrue(meta["send_message"]["requires_confirmation"])
        self.assertTrue(meta["shutdown_jarvis"]["requires_confirmation"])

    def test_registry_built_like_main_gates_correctly(self):
        """Mirror main._build_registry without importing the audio/Gemini stack."""
        meta = json.loads(
            (self.ROOT / "config" / "tools.json").read_text(encoding="utf-8")
        )
        meta = {k: v for k, v in meta.items() if not k.startswith("_")}

        reg = ToolRegistry()
        # Stand-in schemas named like the real tools + the two gate tools.
        names = list(meta.keys()) + ["confirm_action", "cancel_action", "open_app"]
        reg.register_schemas([_schema(n) for n in names])
        reg.apply_metadata(meta)

        # Risky tools are gated; benign ones are not.
        self.assertTrue(reg.requires_confirmation("send_message"))
        self.assertTrue(reg.requires_confirmation("shutdown_jarvis"))
        self.assertFalse(reg.requires_confirmation("web_search"))
        self.assertFalse(reg.requires_confirmation("confirm_action"))

        # The gate tools are always visible to the orchestrator.
        jarvis_names = {d["name"] for d in reg.declarations(agent="jarvis")}
        self.assertIn("confirm_action", jarvis_names)
        self.assertIn("cancel_action", jarvis_names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
