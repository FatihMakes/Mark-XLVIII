"""
core/ollama_backend.py — Local LLM backend for role agents (Ollama / qwen3:14b).

This is a drop-in ``model_fn`` for ``core.role_agent.RoleAgent``: it runs one bounded
turn of a role agent against a local Ollama server (default 127.0.0.1:11434) instead of
Gemini. Because RoleAgent injects its model behind ``model_fn``, switching to a local
model touches **only** this adapter — none of the tier-enforcing code:

  - Tier 2 (least-privilege): the tool list handed to the model is still
    ``REGISTRY.declarations_for(manifest.tools)``, and the dispatch guard is unchanged.
  - Tier 4 (confirmation gate): the gate runs in the orchestrator *before* any model is
    called, so it is independent of the backend.

The work this module actually does:
  - convert our Gemini-style tool declarations (``"type": "OBJECT"``) to the JSON-Schema
    Ollama expects (``"type": "object"``),
  - carry the manifest's system prompt through as a proper ``system`` message,
  - parse the model's ``tool_calls`` back into our ``ModelTurn`` / ``ToolCall`` types,
  - strip qwen3 ``<think>…</think>`` reasoning out of the spoken answer.

The pure helpers and the parser take an injectable client, so everything is unit-tested
without the ``ollama`` package or a running server.
"""

from __future__ import annotations

import json
import re

from core.role_agent import ModelTurn, ToolCall


DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:14b"

# Gemini schema types -> JSON-Schema types Ollama/OpenAI tools expect.
_TYPE_MAP = {
    "OBJECT": "object",
    "STRING": "string",
    "INTEGER": "integer",
    "NUMBER": "number",
    "BOOLEAN": "boolean",
    "ARRAY": "array",
}

_THINK_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


def _get(obj, key, default=None):
    """Attribute-or-key access — Ollama may return pydantic objects or plain dicts."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def convert_schema(node):
    """Recursively lower-case Gemini schema types into JSON-Schema types."""
    if not isinstance(node, dict):
        return node
    out = {}
    for k, v in node.items():
        if k == "type" and isinstance(v, str):
            out[k] = _TYPE_MAP.get(v.upper(), v.lower())
        elif k == "properties" and isinstance(v, dict):
            out[k] = {pk: convert_schema(pv) for pk, pv in v.items()}
        elif k == "items":
            out[k] = convert_schema(v)
        else:
            out[k] = v
    return out


def to_ollama_tool(decl: dict) -> dict:
    """Turn one Gemini function-declaration into an Ollama tool spec."""
    params = convert_schema(decl.get("parameters") or {})
    if not isinstance(params, dict):
        params = {}
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    return {
        "type": "function",
        "function": {
            "name": decl.get("name", ""),
            "description": decl.get("description", ""),
            "parameters": params,
        },
    }


def build_messages(manifest, messages: list[dict]) -> list[dict]:
    """Build the Ollama message list, carrying the system prompt with full fidelity."""
    out: list[dict] = []
    system = manifest.system_prompt or manifest.description
    if system:
        out.append({"role": "system", "content": system})
    for m in messages:
        role = m.get("role", "user")
        if role == "tool":
            out.append(
                {"role": "tool", "content": str(m.get("content", "")),
                 "name": m.get("name", "")}
            )
        elif role == "assistant" and m.get("tool_calls"):
            # Reconstruct the assistant's tool-call turn in Ollama's shape so the
            # following tool results are a valid continuation of the exchange.
            out.append(
                {
                    "role": "assistant",
                    "content": str(m.get("content", "")),
                    "tool_calls": [
                        {"function": {"name": tc.get("name", ""),
                                      "arguments": tc.get("args", {})}}
                        for tc in m["tool_calls"]
                    ],
                }
            )
        else:
            out.append({"role": role, "content": str(m.get("content", ""))})
    return out


def parse_response(resp) -> ModelTurn:
    """Parse an Ollama chat response into a ModelTurn (tool calls or final text)."""
    message = _get(resp, "message", {}) or {}
    calls = []
    for tc in (_get(message, "tool_calls", []) or []):
        fn = _get(tc, "function", {}) or {}
        name = _get(fn, "name", "")
        args = _get(fn, "arguments", {}) or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (ValueError, TypeError):
                args = {}
        if not isinstance(args, dict):
            args = {}
        if name:
            calls.append(ToolCall(name, dict(args)))
    if calls:
        return ModelTurn(tool_calls=tuple(calls))

    content = _get(message, "content", "") or ""
    content = _THINK_RE.sub("", content).strip()
    return ModelTurn(text=content or "Done.")


def ollama_chat(manifest, messages, tool_declarations, *, client=None,
                host: str = DEFAULT_HOST) -> ModelTurn:
    """``model_fn`` for RoleAgent: one bounded turn against local Ollama.

    Any failure degrades to a plain-text ModelTurn so a backend hiccup can never crash
    the orchestrator (Tier 3 — failures cross the boundary as data, not exceptions).
    """
    try:
        if client is None:
            import ollama
            client = ollama.Client(host=host)
        oll_msgs = build_messages(manifest, messages)
        tools = [to_ollama_tool(d) for d in tool_declarations]
        resp = client.chat(
            model=manifest.model or DEFAULT_MODEL,
            messages=oll_msgs,
            tools=tools,
        )
        return parse_response(resp)
    except Exception as e:  # noqa: BLE001 — boundary: convert to data
        return ModelTurn(text=f"Role '{manifest.name}' could not complete (ollama): {e}")
