"""
core/manifest.py — Config-driven agents + live hot-reload (orchestration Tier 6).

An agent is *data*, not a class. A manifest declares everything that makes one agent
different from another:
    - name, description
    - the model it is allowed to use
    - its tool allowlist (least privilege — Tier 2)
    - a bounded-loop cap (max_iterations — Tier 2)

The manifest store is a JSON file on disk (``config/agents.json``). A watcher reloads it
when the file's mtime changes, so you can add, change, or retire an agent at runtime
with no restart: edit the file (or write it programmatically) and the live roster
updates on the next ``reload_if_changed()`` tick.

The "capability" (a dispatch tool the orchestrator can call) and the "definition" (this
manifest) are decoupled: :func:`make_dispatch_tool` turns any manifest into a fresh
Gemini function-declaration, and the registry watcher keeps the live set of dispatch
tools in sync with the manifests.

Pure stdlib — no Gemini, no Qt — so it is testable without the app running.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# A sensible default so a misconfigured manifest can never spin forever (Tier 2).
DEFAULT_MAX_ITERATIONS = 8


@dataclass(frozen=True)
class AgentManifest:
    """One agent, expressed entirely as data."""

    name: str
    description: str = ""
    model: str = "gemini-2.5-flash"
    tools: tuple[str, ...] = ()            # allowlist; ("*",) means every tool
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    system_prompt: str = ""
    active: bool = True
    # --- role-registry fields (orchestration Tier 1 routing) ---------------
    role: str = ""                        # human label e.g. "gold & numbers desk"
    keywords: tuple[str, ...] = ()        # hints the orchestrator routes on
    requires_confirmation: bool = False   # gate dispatch to this agent (e.g. trades)
    dispatchable: bool = False            # expose a dispatch_to_<name> tool for it

    def allows_all_tools(self) -> bool:
        return "*" in self.tools

    def may_use(self, tool_name: str, known_tools: Iterable[str] | None = None) -> bool:
        """True if this agent's allowlist permits ``tool_name``.

        ``"*"`` expands to every currently-known tool when ``known_tools`` is given.
        """
        if self.allows_all_tools():
            if known_tools is None:
                return True
            return tool_name in set(known_tools)
        return tool_name in self.tools

    def allowed_tools(self, known_tools: Iterable[str]) -> list[str]:
        """Resolve this agent's allowlist against the known tool set."""
        known = list(known_tools)
        if self.allows_all_tools():
            return sorted(known)
        return sorted(t for t in self.tools if t in known)

    @staticmethod
    def from_dict(d: dict) -> "AgentManifest":
        return AgentManifest(
            name=d["name"],
            description=d.get("description", ""),
            model=d.get("model", "gemini-2.5-flash"),
            tools=tuple(d.get("tools", ())),
            max_iterations=int(d.get("max_iterations", DEFAULT_MAX_ITERATIONS)),
            system_prompt=d.get("system_prompt", ""),
            active=bool(d.get("active", True)),
            role=d.get("role", ""),
            keywords=tuple(k.lower() for k in d.get("keywords", ())),
            requires_confirmation=bool(d.get("requires_confirmation", False)),
            dispatchable=bool(d.get("dispatchable", False)),
        )


def make_dispatch_tool(manifest: AgentManifest) -> dict:
    """Build a ``dispatch_to_<name>`` Gemini function declaration for an agent.

    This is the dispatch-tool factory from the Tier 6 design: given a manifest, return
    a fresh capability the orchestrator can offer. The watcher registers one of these
    per active agent and removes it when the agent retires.
    """
    return {
        "name": f"dispatch_to_{manifest.name}",
        "description": (
            (manifest.description or f"Hand the task to the {manifest.name} agent.")
            + " Dispatch a single natural-language task to this specialist agent."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {
                    "type": "STRING",
                    "description": "The natural-language task to hand to this agent.",
                }
            },
            "required": ["task"],
        },
    }


class ManifestStore:
    """Loads agent manifests from a JSON file and reloads them on change (Tier 6).

    File format (``config/agents.json``)::

        {"agents": [
            {"name": "task", "model": "...", "tools": ["web_search", ...],
             "max_iterations": 6, "active": true},
            ...
        ]}

    Usage::

        store = ManifestStore(path)
        store.load()                       # initial
        ...
        if store.reload_if_changed():      # cheap mtime check each tick
            roster = store.agents()        # refresh the live set
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._agents: dict[str, AgentManifest] = {}
        self._mtime: float | None = None

    def load(self) -> dict[str, AgentManifest]:
        """Read and parse the manifest file (active agents only)."""
        data = json.loads(self._path.read_text(encoding="utf-8"))
        agents: dict[str, AgentManifest] = {}
        for raw in data.get("agents", []):
            m = AgentManifest.from_dict(raw)
            if m.active:
                agents[m.name] = m
        with self._lock:
            self._agents = agents
            try:
                self._mtime = self._path.stat().st_mtime
            except OSError:
                self._mtime = None
        return dict(agents)

    def reload_if_changed(self) -> bool:
        """Reload if the file's mtime moved. Returns True when a reload happened."""
        try:
            current = self._path.stat().st_mtime
        except OSError:
            return False
        with self._lock:
            unchanged = self._mtime is not None and current == self._mtime
        if unchanged:
            return False
        self.load()
        return True

    def agents(self) -> dict[str, AgentManifest]:
        with self._lock:
            return dict(self._agents)

    def get(self, name: str) -> AgentManifest | None:
        with self._lock:
            return self._agents.get(name)

    def diff(self, previous: dict[str, AgentManifest]) -> tuple[list[str], list[str]]:
        """Compare a previous roster to the current one.

        Returns ``(added, removed)`` agent names — exactly what a registry watcher
        needs to register new ``dispatch_to_<name>`` tools and unregister gone ones.
        """
        current = self.agents()
        added = [n for n in current if n not in previous]
        removed = [n for n in previous if n not in current]
        return sorted(added), sorted(removed)
