"""
core/roles.py — The Role Registry (orchestration Tier 1 dispatch intelligence).

Jarvis is the conductor; the specialists are named roles, each owning one kind of work:

    Eva   — gold / numbers / prices
    Bobby — market news
    Tom   — buy / sell orders   (gated: money moves need a human yes)

The registry is the conductor's map. It does NOT decide alone — Jarvis (the LLM) still
routes — but it provides:
  - a concise routing policy injected into Jarvis's system prompt (one line per role),
  - a keyword-based `route()` hint for logging / fallback,
  - one `dispatch_to_role` tool the orchestrator calls with (role, task).

Key design point from the spec: routing intelligence belongs to the orchestrator alone.
Individual role agents do not know about each other; that knowledge lives here, centrally.

Built on ManifestStore so roles are data and hot-reloadable (Tier 6). Pure stdlib.
"""

from __future__ import annotations

from core.manifest import AgentManifest, ManifestStore


# The orchestrator itself is not a dispatch target.
ORCHESTRATOR_NAME = "jarvis"


class RoleRegistry:
    """A view over agent manifests that are marked ``dispatchable`` (the named roles)."""

    def __init__(self, store: ManifestStore) -> None:
        self._store = store

    # ---- discovery ----------------------------------------------------------

    def roles(self) -> dict[str, AgentManifest]:
        """Active, dispatchable roles (excludes the orchestrator and internal agents)."""
        return {
            name: m
            for name, m in self._store.agents().items()
            if m.dispatchable and name != ORCHESTRATOR_NAME
        }

    def get(self, name: str) -> AgentManifest | None:
        m = self._store.get(name)
        if m and m.dispatchable and name != ORCHESTRATOR_NAME:
            return m
        return None

    def names(self) -> list[str]:
        return sorted(self.roles())

    # ---- routing (Tier 1) ---------------------------------------------------

    def route(self, text: str) -> str | None:
        """Best-effort keyword route. Returns a role name or None if ambiguous/none.

        This is a *hint*, not the decision — Jarvis's LLM does the real routing using
        the policy text. Used for logging and as a deterministic fallback. Returns None
        when zero or more-than-one role match (genuinely ambiguous → ask, don't guess).
        """
        if not text:
            return None
        low = text.lower()
        hits = [
            name
            for name, m in self.roles().items()
            if any(k in low for k in m.keywords)
        ]
        unique = sorted(set(hits))
        return unique[0] if len(unique) == 1 else None

    def routing_policy(self) -> str:
        """One-line-per-role policy for the orchestrator's system prompt."""
        roles = self.roles()
        if not roles:
            return ""
        lines = ["[ROLE REGISTRY — route work to the right specialist]"]
        for name in sorted(roles):
            m = roles[name]
            kw = ", ".join(m.keywords[:6]) if m.keywords else "—"
            gate = " (requires user confirmation — money move)" if m.requires_confirmation else ""
            lines.append(
                f"- {name}: {m.role or m.description}{gate}. Route when about: {kw}."
            )
        lines.append(
            "Call dispatch_to_role(role=<name>, task=<verbatim user request>). "
            "If a request is genuinely ambiguous between two roles, ask ONE short "
            "clarifying question before dispatching. Decompose a multi-part request "
            "into separate dispatches, in order."
        )
        return "\n".join(lines) + "\n\n"

    # ---- the single dispatch tool ------------------------------------------

    def dispatch_tool_declaration(self) -> dict:
        """The one Gemini tool the orchestrator uses to reach any role."""
        names = self.names()
        return {
            "name": "dispatch_to_role",
            "description": (
                "Hand a task to a specialist role from the role registry. "
                "Available roles: " + (", ".join(names) if names else "(none)") + ". "
                "Pass the user's request verbatim as the task."
            ),
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "role": {
                        "type": "STRING",
                        "description": "Target role name: " + (" | ".join(names) if names else ""),
                    },
                    "task": {
                        "type": "STRING",
                        "description": "The natural-language task to hand the role, verbatim.",
                    },
                },
                "required": ["role", "task"],
            },
        }
