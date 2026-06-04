"""
core/audit.py — The black box: an immutable audit trail for every orchestration move.

Why this exists: when a trade wins or loses, you must be able to go back and see EXACTLY
why Jarvis decided what it decided — which role it routed to, what tools ran with what
arguments, whether a confirmation gate was hit, what the human approved, and which
handoff led where. Without this you cannot debug a bad call or learn from it.

Design rules baked in:
  - Record BEFORE acting. A decision is logged as ``pending`` first, then updated to
    ``executed``/``failed`` — so a crash mid-action still leaves a trace of intent.
  - Logging never breaks real work. Every write is failure-isolated: if the DB is
    locked or broken, the method swallows the error and returns None. A broken black
    box must never block the orchestrator (same principle as fire-and-forget observers).
  - Pure stdlib (sqlite3). Thread-safe. Testable against ``:memory:``.

Tables:
  decisions  — one row per orchestration decision (route/dispatch/gate/confirm/run).
  tool_calls — one row per tool invocation (tool, args, result, error), linked to a decision.
  handoffs   — one row per proposed handoff and whether it was accepted.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    actor         TEXT    NOT NULL,          -- jarvis / eva / bobby / tom
    action        TEXT    NOT NULL,          -- route / dispatch / gate / confirm / run / execute
    target_role   TEXT    DEFAULT '',
    task          TEXT    DEFAULT '',
    status        TEXT    DEFAULT 'pending', -- pending / executed / failed / blocked / approved / rejected
    prompt_hash   TEXT    DEFAULT '',        -- which system prompt drove it (sha256[:12])
    detail        TEXT    DEFAULT '',
    result        TEXT    DEFAULT '',
    error         TEXT    DEFAULT ''
);
CREATE TABLE IF NOT EXISTS tool_calls (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    decision_id   INTEGER,
    actor         TEXT    DEFAULT '',
    tool          TEXT    NOT NULL,
    args          TEXT    DEFAULT '{}',
    result        TEXT    DEFAULT '',
    error         TEXT    DEFAULT '',
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
CREATE TABLE IF NOT EXISTS handoffs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL    NOT NULL,
    from_role     TEXT    NOT NULL,
    to_role       TEXT    NOT NULL,
    reason        TEXT    DEFAULT '',
    token         TEXT    DEFAULT '',
    confidence    REAL,
    accepted      INTEGER,                   -- NULL pending, 1 accepted, 0 rejected
    decision_id   INTEGER,
    FOREIGN KEY (decision_id) REFERENCES decisions(id)
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts);
CREATE INDEX IF NOT EXISTS idx_tool_calls_ts ON tool_calls(ts);
"""


def prompt_hash(text: str) -> str:
    """Short stable fingerprint of a system prompt, to track which version ran."""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _dumps(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


class AuditLog:
    """SQLite-backed audit trail. All writes are failure-isolated."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False + our own lock: the orchestrator writes from several
        # threads (executor, role runs, UI callbacks).
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ---- writes -------------------------------------------------------------

    def record_decision(
        self,
        actor: str,
        action: str,
        *,
        target_role: str = "",
        task: str = "",
        status: str = "pending",
        system_prompt: str = "",
        detail: str = "",
    ) -> int | None:
        """Log a decision (defaults to ``pending`` — update it once the action resolves)."""
        return self._insert(
            "INSERT INTO decisions (ts, actor, action, target_role, task, status, "
            "prompt_hash, detail) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), actor, action, target_role, task[:2000], status,
             prompt_hash(system_prompt), detail[:2000]),
        )

    def update_decision(
        self,
        decision_id: int | None,
        *,
        status: str | None = None,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        if decision_id is None:
            return
        sets, vals = [], []
        if status is not None:
            sets.append("status = ?"); vals.append(status)
        if result is not None:
            sets.append("result = ?"); vals.append(str(result)[:4000])
        if error is not None:
            sets.append("error = ?"); vals.append(str(error)[:2000])
        if not sets:
            return
        vals.append(decision_id)
        self._exec(f"UPDATE decisions SET {', '.join(sets)} WHERE id = ?", tuple(vals))

    def record_tool_call(
        self,
        tool: str,
        *,
        decision_id: int | None = None,
        actor: str = "",
        args: dict | None = None,
        result: str = "",
        error: str = "",
    ) -> int | None:
        return self._insert(
            "INSERT INTO tool_calls (ts, decision_id, actor, tool, args, result, error) "
            "VALUES (?,?,?,?,?,?,?)",
            (time.time(), decision_id, actor, tool, _dumps(args or {}),
             str(result)[:4000], str(error)[:2000]),
        )

    def record_handoff(
        self,
        from_role: str,
        to_role: str,
        *,
        reason: str = "",
        token: str = "",
        confidence: float | None = None,
        accepted: bool | None = None,
        decision_id: int | None = None,
    ) -> int | None:
        acc = None if accepted is None else (1 if accepted else 0)
        return self._insert(
            "INSERT INTO handoffs (ts, from_role, to_role, reason, token, confidence, "
            "accepted, decision_id) VALUES (?,?,?,?,?,?,?,?)",
            (time.time(), from_role, to_role, reason[:1000], token, confidence,
             acc, decision_id),
        )

    def resolve_handoff(self, token: str, accepted: bool) -> None:
        self._exec(
            "UPDATE handoffs SET accepted = ? WHERE token = ?",
            (1 if accepted else 0, token),
        )

    # ---- reads (for the dashboard) -----------------------------------------

    def recent_decisions(self, limit: int = 50) -> list[dict]:
        return self._query(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        )

    def recent_tool_calls(self, limit: int = 50) -> list[dict]:
        return self._query(
            "SELECT * FROM tool_calls ORDER BY id DESC LIMIT ?", (limit,)
        )

    def recent_handoffs(self, limit: int = 50) -> list[dict]:
        return self._query(
            "SELECT * FROM handoffs ORDER BY id DESC LIMIT ?", (limit,)
        )

    def stats(self) -> dict:
        """Counts for the dashboard: totals + breakdown by actor and status."""
        out = {"decisions": 0, "tool_calls": 0, "handoffs": 0,
               "by_actor": {}, "by_status": {}}
        try:
            with self._lock:
                out["decisions"] = self._conn.execute(
                    "SELECT COUNT(*) FROM decisions").fetchone()[0]
                out["tool_calls"] = self._conn.execute(
                    "SELECT COUNT(*) FROM tool_calls").fetchone()[0]
                out["handoffs"] = self._conn.execute(
                    "SELECT COUNT(*) FROM handoffs").fetchone()[0]
                for actor, n in self._conn.execute(
                    "SELECT actor, COUNT(*) FROM decisions GROUP BY actor"):
                    out["by_actor"][actor] = n
                for status, n in self._conn.execute(
                    "SELECT status, COUNT(*) FROM decisions GROUP BY status"):
                    out["by_status"][status] = n
        except Exception as e:
            print(f"[Audit] stats failed: {e}")
        return out

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # ---- internals (failure-isolated) --------------------------------------

    def _insert(self, sql: str, params: tuple) -> int | None:
        try:
            with self._lock:
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                return cur.lastrowid
        except Exception as e:  # never let logging break the orchestrator
            print(f"[Audit] write failed: {e}")
            return None

    def _exec(self, sql: str, params: tuple) -> None:
        try:
            with self._lock:
                self._conn.execute(sql, params)
                self._conn.commit()
        except Exception as e:
            print(f"[Audit] update failed: {e}")

    def _query(self, sql: str, params: tuple) -> list[dict]:
        try:
            with self._lock:
                rows = self._conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            print(f"[Audit] query failed: {e}")
            return []
