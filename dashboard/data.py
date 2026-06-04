"""
dashboard/data.py — Read-only data layer for the live dashboard.

The dashboard is a SEPARATE process from Jarvis, so it cannot see the orchestrator's
in-memory state — it reads everything from the audit black box (logs/audit.db) and the
agent manifests (config/agents.json). This module turns those into the rows/cards the
Streamlit UI renders.

Kept pure (no Streamlit import) so the derivation logic — especially "what is each
agent doing right now" — is unit-tested without a browser.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from core.audit import AuditLog
from core.manifest import ManifestStore


# How long after its last activity an agent is still considered "working".
WORKING_WINDOW_SECONDS = 90.0


def agent_roster(store: ManifestStore) -> list[dict]:
    """All agents (orchestrator + roles) as cards, in a stable display order."""
    agents = store.agents()
    order = {"jarvis": 0}  # orchestrator first, then roles alphabetically
    cards = []
    for name, m in agents.items():
        cards.append(
            {
                "name": name,
                "role": m.role or m.description,
                "model": m.model,
                "dispatchable": m.dispatchable,
                "gated": m.requires_confirmation,
                "tools": list(m.tools),
                "max_iterations": m.max_iterations,
            }
        )
    cards.sort(key=lambda c: (order.get(c["name"], 1), c["name"]))
    return cards


def _status_from_decision(decision: dict, now: float) -> str:
    """Map a decision row to a human pulse label."""
    st = decision.get("status", "")
    age = now - float(decision.get("ts", now))
    if st == "blocked":
        return "awaiting confirmation"
    if st == "pending":
        return "working" if age < WORKING_WINDOW_SECONDS else "stalled"
    if st == "failed":
        return "error"
    # executed / approved / rejected / anything else
    return "idle"


def agent_status(audit: AuditLog, names: list[str], scan: int = 300) -> dict[str, dict]:
    """Derive each agent's current pulse from the most recent decision touching it.

    An agent is matched when it is either the actor or the target_role of a decision.
    Newest-first scan means the first match per agent is its latest activity.
    """
    now = time.time()
    out = {
        n: {"status": "idle", "last_task": "", "last_action": "",
            "last_ts": None, "last_status": ""}
        for n in names
    }
    for d in audit.recent_decisions(scan):  # newest first
        for n in names:
            if out[n]["last_ts"] is not None:
                continue
            if d.get("actor") == n or d.get("target_role") == n:
                out[n].update(
                    status=_status_from_decision(d, now),
                    last_task=d.get("task", ""),
                    last_action=d.get("action", ""),
                    last_ts=d.get("ts"),
                    last_status=d.get("status", ""),
                )
    return out


def overview(audit: AuditLog, store: ManifestStore) -> list[dict]:
    """Roster cards merged with live pulse — the top section of the dashboard."""
    roster = agent_roster(store)
    status = agent_status(audit, [c["name"] for c in roster])
    for card in roster:
        card.update(status.get(card["name"], {}))
    return roster


def pending_handoffs(audit: AuditLog, limit: int = 50) -> list[dict]:
    """Proposed handoffs the human has not yet accepted/rejected (accepted IS NULL)."""
    return [h for h in audit.recent_handoffs(limit) if h.get("accepted") is None]


def summary(audit: AuditLog) -> dict[str, Any]:
    return audit.stats()


def fmt_ts(ts: float | None) -> str:
    if not ts:
        return "—"
    return time.strftime("%H:%M:%S", time.localtime(float(ts)))


def default_db_path() -> Path:
    return Path(__file__).resolve().parent.parent / "logs" / "audit.db"


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parent.parent / "config" / "agents.json"
