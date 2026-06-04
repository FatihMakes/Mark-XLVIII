"""
dashboard/app.py — MARK XXXIX live dashboard (read-only).

Shows the "pulse" of the team — Jarvis (orchestrator) and the role agents Eva, Bobby,
Tom — plus the black-box decision log, tool calls and pending handoffs. It is read-only
by design: it watches, it never commands (per the agreed Tier-1 dashboard scope).

Run it (separate process from Jarvis):
    streamlit run dashboard/app.py

It reads logs/audit.db and config/agents.json. If Jarvis hasn't run yet the DB is empty
and the dashboard simply shows the roster with everyone idle.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Make the project root importable when Streamlit runs this file directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from core.audit import AuditLog
from core.manifest import ManifestStore
from dashboard import data as D


st.set_page_config(page_title="MARK XXXIX — Team Pulse", page_icon="🛰️", layout="wide")

_STATUS_STYLE = {
    "working": ("🟢", "#16a34a"),
    "awaiting confirmation": ("🟡", "#d97706"),
    "stalled": ("🟠", "#ea580c"),
    "error": ("🔴", "#dc2626"),
    "idle": ("⚪", "#6b7280"),
}
_ACTOR_ICON = {"jarvis": "🧠", "eva": "🥇", "bobby": "📰", "tom": "💱", "task": "⚙️"}


@st.cache_resource
def _audit(db_path: str) -> AuditLog:
    return AuditLog(db_path)


@st.cache_resource
def _store(manifest_path: str) -> ManifestStore:
    s = ManifestStore(manifest_path)
    try:
        s.load()
    except Exception as e:
        st.warning(f"Could not load manifests: {e}")
    return s


def _agent_card(card: dict) -> None:
    icon = _ACTOR_ICON.get(card["name"], "🤖")
    badge, color = _STATUS_STYLE.get(card.get("status", "idle"), ("⚪", "#6b7280"))
    gated = " · 🔒 gated" if card.get("gated") else ""
    st.markdown(
        f"### {icon} {card['name'].title()} {badge}\n"
        f"<span style='color:{color};font-weight:600'>{card.get('status','idle').upper()}</span>"
        f"{gated}",
        unsafe_allow_html=True,
    )
    st.caption(f"{card.get('role','')}")
    st.caption(f"`{card.get('model','')}`")
    last = card.get("last_task") or "—"
    when = D.fmt_ts(card.get("last_ts"))
    st.write(f"**Last:** {card.get('last_action','—')} · {when}")
    if last and last != "—":
        st.write(f"> {last[:140]}")


def main() -> None:
    st.title("🛰️ MARK XXXIX — Team Pulse")
    st.caption("Read-only view of the orchestrator's black box. It watches; it never commands.")

    with st.sidebar:
        st.header("Settings")
        db_path = st.text_input("Audit DB", str(D.default_db_path()))
        man_path = st.text_input("Manifests", str(D.default_manifest_path()))
        auto = st.checkbox("Auto-refresh", value=True)
        interval = st.slider("Refresh seconds", 2, 30, 5)
        st.button("Refresh now")

    audit = _audit(db_path)
    store = _store(man_path)
    if store.reload_if_changed():
        st.toast("Manifests reloaded")

    stats = D.summary(audit)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Decisions", stats.get("decisions", 0))
    c2.metric("Tool calls", stats.get("tool_calls", 0))
    c3.metric("Handoffs", stats.get("handoffs", 0))
    c4.metric("Executed", stats.get("by_status", {}).get("executed", 0))

    st.subheader("Team")
    cards = D.overview(audit, store)
    cols = st.columns(max(1, len(cards)))
    for col, card in zip(cols, cards):
        with col:
            _agent_card(card)

    pend = D.pending_handoffs(audit)
    if pend:
        st.subheader("⏳ Pending handoffs (awaiting your yes/no)")
        st.dataframe(
            [
                {"from": h["from_role"], "to": h["to_role"], "reason": h["reason"],
                 "confidence": h.get("confidence"), "at": D.fmt_ts(h["ts"])}
                for h in pend
            ],
            use_container_width=True, hide_index=True,
        )

    st.subheader("🧾 Decision log (black box)")
    decisions = audit.recent_decisions(100)
    if decisions:
        st.dataframe(
            [
                {"#": d["id"], "at": D.fmt_ts(d["ts"]), "actor": d["actor"],
                 "action": d["action"], "→ role": d["target_role"],
                 "status": d["status"], "task": (d["task"] or "")[:80],
                 "result": (d["result"] or "")[:80], "prompt": d["prompt_hash"]}
                for d in decisions
            ],
            use_container_width=True, hide_index=True, height=320,
        )
    else:
        st.info("No decisions recorded yet — start Jarvis and route a request.")

    with st.expander("🔧 Recent tool calls"):
        tcs = audit.recent_tool_calls(100)
        if tcs:
            st.dataframe(
                [
                    {"#": t["id"], "at": D.fmt_ts(t["ts"]), "actor": t["actor"],
                     "tool": t["tool"], "args": t["args"],
                     "result": (t["result"] or "")[:80], "error": (t["error"] or "")[:60]}
                    for t in tcs
                ],
                use_container_width=True, hide_index=True,
            )
        else:
            st.caption("No tool calls yet.")

    st.caption(f"Updated {time.strftime('%H:%M:%S')}")

    if auto:
        time.sleep(interval)
        st.rerun()


if __name__ == "__main__":
    main()
