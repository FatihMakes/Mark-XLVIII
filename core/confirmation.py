"""
core/confirmation.py — Human-in-the-loop confirmation gates (orchestration Tier 4).

The problem this solves: MARK XXXIX can send WhatsApp/Telegram messages to real
people, shut the machine down, and delete files — today all of that runs the instant
the model decides to. One hallucinated tool call is one very bad day.

The gate makes "almost did something dumb" into "asked first". When a tool marked
``requires_confirmation`` is called, the router does NOT run it. Instead it parks the
call here and hands back a ``confirmation_required`` payload the model voices to the
user ("Sir, this will send 'X' to John on WhatsApp — shall I proceed?"). Only when the
human says yes does the model call the separate ``confirm_action`` path, which runs the
parked call exactly once.

Key design point (from the orchestration spec): the gate lives in the router, not
inside each tool. Tools stay simple; the orchestration layer owns "should this even
run yet". This store is the router's memory of what is waiting.

Pure stdlib — thread-safe, no app imports — so it is trivially testable.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PendingAction:
    """One tool call frozen at the gate, awaiting a human yes/no."""

    token: str
    tool: str
    args: dict
    agent: str | None = None
    created_at: float = field(default_factory=time.time)

    def summary(self) -> str:
        """A short, human-readable description the model can voice."""
        if self.args:
            pairs = ", ".join(f"{k}={v!r}" for k, v in self.args.items())
            return f"{self.tool}({pairs})"
        return f"{self.tool}()"


class ConfirmationStore:
    """Holds tool calls that are waiting for explicit human approval.

    Lifecycle:
        token = store.stage(tool, args)        # router parks a gated call
        ...                                     # model voices the prompt, user replies
        pending = store.approve(token)          # -> PendingAction, removed from store
        # or
        store.reject(token)                     # -> drops it
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._pending: dict[str, PendingAction] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def stage(self, tool: str, args: dict, agent: str | None = None) -> PendingAction:
        """Park a tool call and return the PendingAction (carrying its token)."""
        self._evict_expired()
        token = uuid.uuid4().hex[:8]
        action = PendingAction(token=token, tool=tool, args=dict(args), agent=agent)
        with self._lock:
            self._pending[token] = action
        return action

    def confirmation_payload(self, action: PendingAction) -> dict:
        """The structured result the router returns instead of running the tool.

        Returning this (rather than a plain string) keeps the gate machine-readable:
        the model can see it must ask, and what token to confirm with.
        """
        return {
            "confirmation_required": True,
            "token": action.token,
            "tool": action.tool,
            "args": action.args,
            "summary": action.summary(),
            "message": (
                f"This will run {action.summary()}. "
                f"Confirm with confirm_action(token='{action.token}') only after the "
                f"user explicitly approves."
            ),
        }

    def approve(self, token: str) -> PendingAction | None:
        """Pop and return the pending action, or None if the token is unknown/expired."""
        self._evict_expired()
        with self._lock:
            return self._pending.pop(token, None)

    def reject(self, token: str) -> bool:
        """Drop a pending action. Returns True if something was waiting."""
        with self._lock:
            return self._pending.pop(token, None) is not None

    def pending(self) -> list[PendingAction]:
        self._evict_expired()
        with self._lock:
            return list(self._pending.values())

    def _evict_expired(self) -> None:
        if self._ttl <= 0:
            return
        cutoff = time.time() - self._ttl
        with self._lock:
            stale = [t for t, a in self._pending.items() if a.created_at < cutoff]
            for t in stale:
                self._pending.pop(t, None)
