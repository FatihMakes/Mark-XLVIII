# MARK XXXIX — Orchestration Layer

This document maps the six-tier orchestration design onto MARK XXXIX and records what
is built, where it lives, and how to extend it.

## What MARK XXXIX actually is

A **single-agent** voice assistant. Gemini 2.5 Flash (native audio) is the
orchestrator; it function-calls into a flat set of tools declared in
`main.py:TOOL_DECLARATIONS` and dispatched in `JarvisLive._dispatch`. The one
sub-agent is the **autonomous task executor** (`agent/executor.py`), reached via the
`agent_task` tool through a threaded priority queue (`agent/task_queue.py`).

## The orchestration core (`core/`)

Three pure-stdlib modules — no Gemini, no Qt, no app imports — so they are unit-tested
without the app running (`tests/core/test_orchestration.py`, run with
`python -m unittest tests.core.test_orchestration -v`).

| Module | Responsibility |
|---|---|
| `core/registry.py` | One source of truth: tool name → schema + handler + metadata (allowlist, confirmation, destructive). Replaces the two hand-maintained dispatch tables. |
| `core/confirmation.py` | Stages risky tool calls and resolves them on explicit human approval. |
| `core/manifest.py` | Agents-as-data: model, tool allowlist, iteration cap. Hot-reloads from `config/agents.json`. |

Config (the declarative source of truth):

- `config/tools.json` — per-tool metadata: which agents may call it, whether it needs
  confirmation, whether it is destructive.
- `config/agents.json` — agent manifests (`jarvis`, `task`).

## Tier-by-tier status

| Tier | Status | Where |
|---|---|---|
| 1 — Smart routing | **Built** (Role Registry) | `core/roles.py`; routing policy in Jarvis system prompt |
| 2 — Least-privilege + bounds | **Built** | `core/registry.py` allowlists; `config/agents.json` caps; `agent/executor.py` + `core/role_agent.py` bounded loops |
| 3 — Failure isolation | Pre-existing + hardened | `_dispatch` try/except; `registry.dispatch` & role model_fn return errors as data |
| 4 — Confirmation gates | **Built** | `core/confirmation.py`; gate in `JarvisLive._execute_tool` and `_run_role` (Tom) |
| 5 — Handoff system | **Built** | `core/handoff.py`; `propose_handoff` tool + `accept_handoff`/`reject_handoff` |
| 6 — Hot-reload | **Built (foundation)** | `core/manifest.py` (`ManifestStore`, `make_dispatch_tool`) |

## The Role Registry — Jarvis as orchestrator

Jarvis no longer does specialist work itself; it routes to **named roles** defined as
manifests in `config/agents.json`:

| Role | Owns | Tools | Gated? |
|---|---|---|---|
| **Eva** | gold / numbers / prices | `web_search`, `file_controller` | no |
| **Bobby** | market news | `web_search`, `browser_control`, `file_controller` | no |
| **Tom** | buy / sell orders | `web_search` | **yes** (money move) |

How a turn flows:

1. `core/roles.py:RoleRegistry.routing_policy()` injects a one-line-per-role policy into
   Jarvis's system prompt (Tier 1). Jarvis calls `dispatch_to_role(role, task)`.
2. `JarvisLive._run_role` looks up the manifest and runs the **generic**
   `core/role_agent.py:RoleAgent` — one bounded tool-use loop (`max_iterations` from the
   manifest), scoped to the manifest's tool allowlist. No bespoke class per role.
3. If the role is `requires_confirmation` (Tom), the call is staged behind the Tier-4
   gate first — a trade never runs without an explicit human yes.
4. A role may call `propose_handoff(target_role, task, …)` to suggest the next step.
   The loop captures it and stops; `core/handoff.py:HandoffStore` parks it and Jarvis
   voices the offer. Only on `accept_handoff(token)` does the next role run — and if
   that target is gated (Tom), its own gate still applies. Roles never dispatch roles.

Routing example (the design the user asked for): "gold price" → Eva, "market news" →
Bobby, "sell my position" → Tom.

## Tier 2 — least privilege, in practice

The **autonomous task agent is intentionally de-scoped**: `config/agents.json` gives
`task` an allowlist that **excludes** `send_message`, `shutdown_jarvis`,
`game_updater`, and `computer_settings`. `agent/executor.py:_call_tool` enforces this —
the executor can no longer message real people or power off the machine with no human
in the loop. If the planner emits a forbidden tool, the call raises and flows into the
normal step-recovery (replan/abort) path. If the manifest can't be read, the executor
falls back to a conservative hardcoded allowlist rather than opening everything.

## Tier 4 — the confirmation gate, in practice

Tools flagged `requires_confirmation` in `config/tools.json` (`send_message`,
`shutdown_jarvis`, `game_updater`) never run on first call. `JarvisLive._execute_tool`:

1. Stages the call in `ConfirmationStore` and returns a `confirmation_required`
   payload (with a `token`) instead of executing.
2. The model voices the prompt and waits (a one-line policy in the system instruction
   enforces "ask, don't assume").
3. On an explicit yes the model calls `confirm_action(token)` → the staged call runs
   **exactly once** via `_dispatch`. On no it calls `cancel_action(token)`.

The gate lives in the router, not inside the tools — so every tool benefits and the
logic is in one place.

## Extending the system

**Make a tool require confirmation:** add it to `config/tools.json` with
`"requires_confirmation": true`. No code change.

**Restrict a tool to certain agents:** set `"agents": ["jarvis"]` (etc.) in
`config/tools.json`, and/or edit the agent's `tools` list in `config/agents.json`.

**Add a role at runtime (Tier 6):** append a manifest to `config/agents.json` with
`"dispatchable": true`, `"keywords": [...]`, a `"system_prompt"`, and a `"tools"`
allowlist. `ManifestStore.reload_if_changed()` picks up the mtime change;
`RoleRegistry` immediately exposes it in routing. (The live session rebuilds the
routing policy and `dispatch_to_role` role list on the next reconnect; wiring an
in-session watcher that refreshes without a reconnect is the remaining polish for full
Tier 6.)

**Wire Tom to a real broker:** give the `tom` manifest a real trade tool in its
allowlist and bind that tool's handler in `JarvisLive._bind_role_tool_handlers`. The
Tier-4 gate already guarantees no order runs without explicit human confirmation.

## Local LLM backend (Ollama / qwen3:14b)

Role agents run on a **local** model by default; `ROLE_LLM_BACKEND` in `main.py`
(`"ollama"` | `"gemini"`) selects the backend, and each role's `model` in
`config/agents.json` names the local model (`qwen3:14b`).

- `core/ollama_backend.py` is a drop-in `model_fn` for `RoleAgent`. It converts our
  Gemini-style tool schemas (`"type": "OBJECT"`) to JSON-Schema (`"object"`), carries
  the manifest's `system_prompt` through as a `system` message, parses `tool_calls`
  back into `ToolCall`s, and strips qwen3 `<think>…</think>` from the spoken answer.
- **Tiers 2 & 4 are untouched by the swap.** The tool allowlist
  (`declarations_for(manifest.tools)`), the dispatch guard, and the confirmation gate
  all run in the orchestrator *around* the model — switching the backend only changes
  which model runs a turn. This is enforced by tests
  (`test_tier2_allowlist_holds_on_ollama`).
- The voice front-end (`JarvisLive`) **stays on Gemini** — `qwen3:14b` has no
  native-audio modality, so it cannot drive the live mic/speaker session.
- Multi-turn tool use requires the assistant's tool-call turn to precede the tool
  result in history; `RoleAgent` records it and `build_messages` reconstructs it in
  Ollama's shape. Without it, a local model re-calls the same tool to the iteration cap.

## Telegram alerts

`core/telegram.py` sends text messages to a configured Telegram chat via the Bot API.
Used by the scheduler (Eva daemon) and by roles that want to push alerts (Bobby news
alerts, Eva price alerts). To configure, add to `config/api_keys.json`:

```json
{"telegram": {"bot_token": "123456:ABC-DEF...", "chat_id": "your_chat_id"}}
```

The `send_alert` tool is scoped to `jarvis`, `eva`, and `bobby` in `config/tools.json`.

## Gold watcher daemon

`core/scheduler.py:GoldWatcher` runs in a background thread, started automatically in
`main()`. Every 15 minutes (configurable) it:

1. Fetches the live gold price via `tradingview_ta`
2. Records a heartbeat in `audit.db` (visible on the dashboard)
3. If price moved more than 0.3% since last check, sends a Telegram alert
4. On strong signals (`STRONG_BUY`/`STRONG_SELL`) or big moves, optionally runs a full
   Eva analysis for a richer read

The daemon is failure-isolated — a crashed tick logs the error and schedules the next one.
Stop it with `gold_watcher.stop()` on shutdown.

## Live market tool (TradingView)

`core/tradingview.py` gives a role (or Jarvis) a live market read — price, the
BUY/SELL/NEUTRAL recommendation, and key indicators (RSI, MACD, EMAs) — via the
`tradingview_ta` library. It is registered as the `tradingview` tool and added to the
**eva** and **tom** allowlists (`config/agents.json` + `config/tools.json`):

- **Eva** uses it for the gold/numbers desk (e.g. "live gold read on 15m").
- **Tom** uses it to see the live price + signal *before* describing an order. It does
  **not** place orders — Tom's Tier-4 confirmation gate still governs any trade.

Symbol resolution maps common names to the right exchange/screener (notably gold =
`OANDA`/`cfd`, not `forex`); intervals normalise from many forms ("15", "15min",
"1 hour"). The network call is failure-isolated (errors come back as data). Pure logic
is unit-tested with an injected fake handler (`tests/core/test_tradingview.py`);
verified live against XAUUSD. Two integration paths to the TradingView **MCP** (Jarvis
as MCP client, or this local adapter) are noted in memory — this ships the local
adapter, which is self-contained.

## The black box (audit trail)

`core/audit.py` is a SQLite-backed audit trail at `logs/audit.db`. Every orchestration
move is recorded so a won/lost trade can be replayed and learned from:

- **decisions** — one row per route / dispatch / gate / confirm / execute, with the
  actor, target role, task, status, and a fingerprint (`prompt_hash`) of the system
  prompt that drove it.
- **tool_calls** — every tool invocation (tool, args, result, error), linked to its
  decision.
- **handoffs** — every proposed handoff and whether the human accepted it.

Two rules make it trustworthy:

1. **Record before acting.** A decision is logged `pending` first, then updated to
   `executed` / `failed` — so a crash mid-action still leaves the intent on record.
2. **Logging never breaks work.** Every write is failure-isolated; a locked or broken
   DB degrades quietly (returns `None`, prints a warning) and never raises into the
   orchestrator.

Wired in `main.py`: `_run_role` opens a decision and records each tool call under it;
the confirmation gate logs `gate`/`confirm` events; `accept_handoff`/`reject_handoff`
resolve the handoff row. Reads (`recent_decisions`, `recent_tool_calls`,
`recent_handoffs`, `stats`) are what the dashboard will render. The DB is gitignored
(`logs/.gitignore`).

## The live dashboard (read-only)

`dashboard/app.py` is a Streamlit dashboard showing the team's pulse. Launch it as a
separate process (it never commands — watch only):

```
run_dashboard.bat            # or: streamlit run dashboard/app.py
```

It reads `logs/audit.db` and `config/agents.json` and shows: per-agent status cards
(Jarvis/Eva/Bobby/Tom — working / awaiting-confirmation / idle, with model + gated
flag), header metrics, pending handoffs awaiting a yes/no, the decision log, and recent
tool calls. Auto-refreshes on an interval. If Jarvis hasn't run, it shows the roster
all-idle.

The derivation logic lives in `dashboard/data.py` (pure, no Streamlit) and is unit
tested in `tests/dashboard/test_data.py` — the "what is each agent doing right now"
mapping is tested without a browser.

## Testing

```
python -m unittest discover -s tests -t . -v
```

Covers orchestration, roles, the local Ollama backend, the audit black box, the
dashboard data layer, the Telegram adapter, the TradingView tool, and the gold watcher
daemon (100 tests, stdlib only — no Gemini, Ollama, Qt, or browser needed).

40 tests, stdlib only — they cover allowlist scoping, failure isolation, the
confirmation gate, the bounded role loop, keyword routing, and the handoff lifecycle,
all without Gemini or Qt.

## Note on packaging

`agent/__init__.py` was added so the local `agent` package wins over any unrelated
`agent` package installed in site-packages (Python prefers a regular package on an
earlier `sys.path` entry). Without it, `from agent.task_queue import ...` could resolve
to the wrong package.
