"""
core/role_agent.py — One generic role-agent runtime (orchestration Tiers 2 & 6).

There is no bespoke class per role. A single ``RoleAgent`` takes a manifest (system
prompt, model, tool allowlist, iteration cap) and runs the standard bounded tool-use
loop. Adding a role = adding a manifest (Tier 6); the loop is always the same.

Bounded by construction (Tier 2):
  - the loop stops at ``manifest.max_iterations`` and returns a clear "didn't converge"
    result instead of spinning,
  - the agent only ever sees the tools its manifest allows (passed in pre-filtered),
  - every tool call is dispatched through ``dispatch_fn``, which isolates failures
    (Tier 3) — a throwing tool comes back as a string, never as an exception that
    kills the loop.

The model is injected as ``model_fn`` so the control flow is testable with a scripted
fake — no Gemini, no network. The real Gemini adapter is wired in ``main.py``.

The agent may end a turn by proposing a handoff (Tier 5) via the always-available
``propose_handoff`` tool; the loop captures it and stops. It never dispatches another
agent itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from core.handoff import HandoffRecommendation
from core.manifest import AgentManifest


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict


@dataclass(frozen=True)
class ModelTurn:
    """What the (injected) model returned for one turn.

    If ``tool_calls`` is non-empty the agent wants to run tools and continue;
    otherwise ``text`` is its final answer.
    """

    tool_calls: tuple[ToolCall, ...] = ()
    text: str = ""


# model_fn(manifest, messages, tool_declarations) -> ModelTurn
ModelFn = Callable[[AgentManifest, list[dict], list[dict]], ModelTurn]
# dispatch_fn(tool_name, args) -> result string  (wraps registry.dispatch, isolates errors)
DispatchFn = Callable[[str, dict], str]


@dataclass
class RoleResult:
    role: str
    result: str
    iterations: int
    converged: bool
    handoff: HandoffRecommendation | None = None
    transcript: list[dict] = field(default_factory=list)


# The handoff tool every role can call to propose (not perform) a next step.
PROPOSE_HANDOFF_TOOL = {
    "name": "propose_handoff",
    "description": (
        "Propose (do NOT perform) handing the next step to another role. The orchestrator "
        "will ask the human before any dispatch. Pass references (paths/IDs/URLs) as "
        "artifacts, never large inline content."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target_role": {"type": "STRING", "description": "Role that should take the next step"},
            "reason": {"type": "STRING", "description": "One sentence: why hand off"},
            "task": {"type": "STRING", "description": "The task to pass that role verbatim"},
            "artifacts": {"type": "OBJECT", "description": "name -> path/ID/URL references"},
            "preconditions": {"type": "ARRAY", "items": {"type": "STRING"},
                              "description": "Things the human should verify first"},
            "confidence": {"type": "NUMBER", "description": "0..1 how strongly you vouch"},
        },
        "required": ["target_role", "task"],
    },
}


class RoleAgent:
    """Runs one manifest's bounded tool-use loop."""

    def __init__(
        self,
        manifest: AgentManifest,
        tool_declarations: list[dict],
        dispatch_fn: DispatchFn,
        model_fn: ModelFn,
    ) -> None:
        self.manifest = manifest
        # The agent sees its allowlisted tools plus the handoff proposal tool.
        self.tool_declarations = list(tool_declarations) + [PROPOSE_HANDOFF_TOOL]
        self.dispatch_fn = dispatch_fn
        self.model_fn = model_fn

    def run(self, task: str) -> RoleResult:
        cap = max(1, self.manifest.max_iterations)
        messages: list[dict] = [{"role": "user", "content": task}]
        transcript: list[dict] = []

        for i in range(1, cap + 1):
            turn = self.model_fn(self.manifest, messages, self.tool_declarations)

            # No tool calls -> the model gave its final answer.
            if not turn.tool_calls:
                return RoleResult(
                    role=self.manifest.name,
                    result=turn.text or "Done.",
                    iterations=i,
                    converged=True,
                    transcript=transcript,
                )

            # Record the assistant's tool-call turn so the next turn's history is a valid
            # tool-use exchange (assistant calls -> tool results). Without this, models
            # following the OpenAI/Ollama protocol see orphaned tool results and just
            # re-call the same tool until the iteration cap.
            messages.append(
                {
                    "role": "assistant",
                    "content": turn.text or "",
                    "tool_calls": [
                        {"name": c.name, "args": dict(c.args)} for c in turn.tool_calls
                    ],
                }
            )

            for call in turn.tool_calls:
                # A handoff proposal ends the turn — propose, don't chain (Tier 5).
                if call.name == "propose_handoff":
                    reco = HandoffRecommendation.from_dict(call.args)
                    transcript.append({"tool": "propose_handoff", "args": call.args})
                    return RoleResult(
                        role=self.manifest.name,
                        result=turn.text or "Proposing a handoff.",
                        iterations=i,
                        converged=True,
                        handoff=reco,
                        transcript=transcript,
                    )

                # Normal tool: dispatch (failure-isolated) and feed the result back.
                result = self.dispatch_fn(call.name, dict(call.args))
                transcript.append({"tool": call.name, "args": call.args, "result": result})
                messages.append(
                    {"role": "tool", "name": call.name, "content": str(result)}
                )

        # Bounded-loop exhaustion (Tier 2): stop cleanly, do not spin.
        return RoleResult(
            role=self.manifest.name,
            result=(
                f"{self.manifest.name} did not converge within {cap} steps; "
                f"stopping cleanly so nothing runs away."
            ),
            iterations=cap,
            converged=False,
            transcript=transcript,
        )
