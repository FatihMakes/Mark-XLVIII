"""
core/registry.py — The single shared tool registry (orchestration Tier 2 backbone).

The problem this solves: MARK XXXIX wired its tools by hand in TWO places —
``main._execute_tool`` (what JARVIS runs) and ``agent.executor._call_tool`` (what the
autonomous task agent runs). The two lists drifted apart, and neither could express
"who is allowed to call this" or "does this need a human's yes first".

This module is the one source of truth. A tool is registered once with:
  - its Gemini function-declaration schema (what the model sees),
  - a handler (bound late by the app, since handlers need live UI/session refs),
  - metadata: which agents may use it, whether it is destructive / needs confirmation.

Everything else in the orchestration layer is a *view* over this registry:
  - Tier 1 routes over the names here,
  - Tier 2 filters these into per-agent allowlists,
  - Tier 4 reads ``requires_confirmation`` here,
  - Tier 6 registers new dispatch tools here at runtime.

Pure stdlib — no Gemini, no Qt, no app imports — so it is trivially testable.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterable


# A handler takes the call arguments plus an opaque context object the app passes
# through (in MARK XXXIX that is the JarvisLive instance) and returns a string.
Handler = Callable[[dict, Any], str]


class ToolError(Exception):
    """Raised for registry-level problems (unknown tool, no handler bound)."""


@dataclass(frozen=True)
class ToolSpec:
    """Everything the orchestrator needs to know about one tool."""

    name: str
    schema: dict                       # full Gemini function declaration dict
    handler: Handler | None = None     # bound late via Registry.bind()
    agents: tuple[str, ...] = ()       # allowlist; empty == every agent may use it
    requires_confirmation: bool = False
    destructive: bool = False
    model: str | None = None           # optional per-tool model hint

    def available_to(self, agent: str | None) -> bool:
        """True if ``agent`` is permitted to use this tool.

        ``agent is None`` means "no scoping" (the top-level orchestrator) and sees
        everything. An empty ``agents`` tuple means the tool is unscoped.
        """
        if agent is None or not self.agents:
            return True
        return agent in self.agents


class ToolRegistry:
    """Thread-safe registry mapping tool name -> ToolSpec.

    Designed so registration (schema + metadata) and handler binding can happen at
    different times: the schemas/metadata can be declared as data up front, while the
    handlers are bound once the live app objects exist.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._lock = threading.RLock()

    # ---- registration -------------------------------------------------------

    def register(self, spec: ToolSpec) -> None:
        with self._lock:
            self._tools[spec.name] = spec

    def register_schema(self, schema: dict) -> None:
        """Register a tool from a raw Gemini function-declaration dict.

        Metadata (agents/confirmation/destructive) defaults to "unscoped, safe" and
        can be layered on later via :meth:`apply_metadata`.
        """
        name = schema.get("name")
        if not name:
            raise ToolError("function declaration is missing a 'name'")
        self.register(ToolSpec(name=name, schema=schema))

    def register_schemas(self, schemas: Iterable[dict]) -> None:
        for s in schemas:
            self.register_schema(s)

    def apply_metadata(self, metadata: dict[str, dict]) -> None:
        """Layer confirmation/allowlist/destructive metadata onto registered tools.

        ``metadata`` maps tool name -> {agents, requires_confirmation, destructive,
        model}. Unknown tool names are ignored (they may belong to a future build),
        so config and code can evolve independently.
        """
        with self._lock:
            for name, meta in metadata.items():
                spec = self._tools.get(name)
                if spec is None:
                    continue
                self._tools[name] = replace(
                    spec,
                    agents=tuple(meta.get("agents", spec.agents)),
                    requires_confirmation=bool(
                        meta.get("requires_confirmation", spec.requires_confirmation)
                    ),
                    destructive=bool(meta.get("destructive", spec.destructive)),
                    model=meta.get("model", spec.model),
                )

    def bind(self, name: str, handler: Handler) -> None:
        """Attach a live handler to an already-registered tool."""
        with self._lock:
            spec = self._tools.get(name)
            if spec is None:
                raise ToolError(f"cannot bind handler: unknown tool '{name}'")
            self._tools[name] = replace(spec, handler=handler)

    def unregister(self, name: str) -> bool:
        """Remove a tool (used by Tier 6 hot-reload when an agent retires)."""
        with self._lock:
            return self._tools.pop(name, None) is not None

    # ---- queries ------------------------------------------------------------

    def get(self, name: str) -> ToolSpec:
        with self._lock:
            spec = self._tools.get(name)
        if spec is None:
            raise ToolError(f"unknown tool '{name}'")
        return spec

    def has(self, name: str) -> bool:
        with self._lock:
            return name in self._tools

    def names(self, agent: str | None = None) -> list[str]:
        with self._lock:
            return sorted(
                n for n, s in self._tools.items() if s.available_to(agent)
            )

    def requires_confirmation(self, name: str) -> bool:
        return self.get(name).requires_confirmation

    def declarations_for(self, names: Iterable[str]) -> list[dict]:
        """Return declaration dicts for an explicit set of tool names (allowlist).

        Used to scope a role agent to exactly its manifest's tool list, independent of
        the per-tool ``agents`` field (which scopes the flat jarvis/task agents).
        """
        wanted = set(names)
        with self._lock:
            specs = [s for s in self._tools.values() if s.name in wanted]
        return [s.schema for s in sorted(specs, key=lambda s: s.name)]

    def declarations(self, agent: str | None = None) -> list[dict]:
        """Return Gemini function-declaration dicts filtered to ``agent``'s allowlist.

        This is what replaces the hand-maintained ``TOOL_DECLARATIONS`` list: build it
        from the registry so there is exactly one source of truth.
        """
        with self._lock:
            specs = [s for s in self._tools.values() if s.available_to(agent)]
        return [s.schema for s in sorted(specs, key=lambda s: s.name)]

    # ---- dispatch -----------------------------------------------------------

    def dispatch(self, name: str, args: dict, ctx: Any, agent: str | None = None) -> str:
        """Run a tool's handler with least-privilege + failure isolation (Tier 2/3).

        - Enforces the per-agent allowlist (raises if ``agent`` may not call ``name``).
        - Never lets a handler exception escape: failures come back as a string
          ``"Tool 'x' failed: ..."`` so the model can read and react instead of the
          whole turn crashing.

        Note: the confirmation gate (Tier 4) lives one layer up, in the router, so
        that the *decision* to even run is made before we reach a handler.
        """
        spec = self.get(name)
        if not spec.available_to(agent):
            raise ToolError(
                f"agent '{agent}' is not permitted to use tool '{name}'"
            )
        if spec.handler is None:
            raise ToolError(f"tool '{name}' has no handler bound")
        try:
            return spec.handler(args, ctx)
        except Exception as e:  # noqa: BLE001 — boundary: convert to data
            return f"Tool '{name}' failed: {e}"
