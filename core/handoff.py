"""
core/handoff.py — The handoff system (orchestration Tier 5): propose, don't chain.

The most tempting multi-agent pattern is also the most dangerous: agent A finishes and
auto-calls agent B, which auto-calls agent C. Errors compound invisibly three hops deep
with no human checkpoint.

So in MARK XXXIX agents never dispatch each other. When a role agent (Eva, Bobby, Tom)
finishes, it may *propose* a next step as a typed HandoffRecommendation. The orchestrator
(Jarvis) voices it as a conversational offer and waits. Only on an explicit human yes
does Jarvis dispatch the target role. The human is the circuit-breaker on every edge.

Artifacts ride as **references** (paths/IDs/URLs), never inline blobs, so a handoff stays
small and serializable into the event stream.

Pure stdlib — thread-safe, no app imports — so it is trivially testable.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class HandoffRecommendation:
    """One agent's proposal for the next step. The human approves or drops it."""

    target_role: str                       # which role should take the next step
    reason: str                            # one human sentence on WHY (Jarvis voices it)
    task: str                              # the task to pass the target verbatim
    artifacts: dict = field(default_factory=dict)   # name -> path/ID/URL references
    preconditions: tuple[str, ...] = ()    # things the human should verify first
    confidence: float = 0.5                # 0..1 — used to phrase the offer

    def offer_text(self) -> str:
        """Phrase the offer to the human; confidence shapes how strongly."""
        if self.confidence >= 0.75:
            lead = "I'd strongly suggest handing this to"
        elif self.confidence >= 0.4:
            lead = "You might want to hand this to"
        else:
            lead = "Optionally, I could pass this to"
        line = f"{lead} {self.target_role}: {self.reason}"
        if self.preconditions:
            line += " (first verify: " + "; ".join(self.preconditions) + ")"
        return line

    @staticmethod
    def from_dict(d: dict | None) -> "HandoffRecommendation | None":
        """Parse a recommendation from model/tool output. Returns None if unusable.

        Tolerant by design: a malformed or empty proposal becomes None (no handoff)
        rather than raising — a bad proposal must never break the turn.
        """
        if not d:
            return None
        target = (d.get("target_role") or d.get("target_agent") or "").strip()
        task = (d.get("task") or "").strip()
        if not target or not task:
            return None
        try:
            confidence = float(d.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))
        artifacts = d.get("artifacts") or {}
        if not isinstance(artifacts, dict):
            artifacts = {}
        preconditions = d.get("preconditions") or ()
        if isinstance(preconditions, str):
            preconditions = (preconditions,)
        return HandoffRecommendation(
            target_role=target,
            reason=(d.get("reason") or "next step").strip(),
            task=task,
            artifacts=dict(artifacts),
            preconditions=tuple(preconditions),
            confidence=confidence,
        )


@dataclass(frozen=True)
class PendingHandoff:
    token: str
    reco: HandoffRecommendation
    source_role: str = ""
    created_at: float = field(default_factory=time.time)


class HandoffStore:
    """Holds proposed handoffs awaiting the human's yes/no (mirror of ConfirmationStore)."""

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        self._pending: dict[str, PendingHandoff] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def propose(self, reco: HandoffRecommendation, source_role: str = "") -> PendingHandoff:
        self._evict_expired()
        token = uuid.uuid4().hex[:8]
        ph = PendingHandoff(token=token, reco=reco, source_role=source_role)
        with self._lock:
            self._pending[token] = ph
        return ph

    def payload(self, ph: PendingHandoff) -> dict:
        """Structured offer the orchestrator returns so the model knows to ask first."""
        r = ph.reco
        return {
            "handoff_proposed": True,
            "token": ph.token,
            "target_role": r.target_role,
            "task": r.task,
            "reason": r.reason,
            "artifacts": r.artifacts,
            "preconditions": list(r.preconditions),
            "confidence": r.confidence,
            "offer": r.offer_text(),
            "message": (
                f"Propose handoff to {r.target_role}. Voice this offer and wait. "
                f"On the user's yes call accept_handoff(token='{ph.token}'); "
                f"on no call reject_handoff(token='{ph.token}'). Do NOT dispatch otherwise."
            ),
        }

    def accept(self, token: str) -> PendingHandoff | None:
        self._evict_expired()
        with self._lock:
            return self._pending.pop(token, None)

    def reject(self, token: str) -> bool:
        with self._lock:
            return self._pending.pop(token, None) is not None

    def pending(self) -> list[PendingHandoff]:
        self._evict_expired()
        with self._lock:
            return list(self._pending.values())

    def _evict_expired(self) -> None:
        if self._ttl <= 0:
            return
        cutoff = time.time() - self._ttl
        with self._lock:
            for t in [t for t, p in self._pending.items() if p.created_at < cutoff]:
                self._pending.pop(t, None)
