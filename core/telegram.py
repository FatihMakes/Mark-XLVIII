"""
core/telegram.py — Telegram Bot API adapter for alert delivery.

Sends text messages to a configured Telegram chat via the Bot API (HTTP POST).
Used by the scheduler (Eva daemon) and by roles that want to push alerts
(Bobby news alerts, Eva price alerts). Does NOT replace the desktop-level
send_message action — that uses pyautogui to type into the Telegram app.

Configuration: reads bot_token and chat_id from config/api_keys.json under a
"telegram" key:  {"telegram": {"bot_token": "123:ABC...", "chat_id": "456789"}}

Failure-isolated: never raises into the caller. Returns a result dict with
ok/error so the orchestrator or daemon can log the outcome without crashing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def _load_config() -> dict:
    """Load telegram config from api_keys.json. Returns {} on any failure."""
    try:
        data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return data.get("telegram", {})
    except Exception:
        return {}


def send_message(
    text: str,
    *,
    bot_token: str = "",
    chat_id: str = "",
    parse_mode: str = "Markdown",
) -> dict[str, Any]:
    """Send a message via the Telegram Bot API.

    Falls back to config/api_keys.json if bot_token/chat_id not passed.
    Returns {"ok": True, "message_id": ...} or {"ok": False, "error": ...}.
    Never raises.
    """
    cfg = _load_config()
    token = bot_token or cfg.get("bot_token", "")
    cid = chat_id or cfg.get("chat_id", "")

    if not token or not cid:
        return {"ok": False, "error": "Telegram not configured (missing bot_token or chat_id in config/api_keys.json → telegram)"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": cid, "text": text, "parse_mode": parse_mode},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            return {"ok": True, "message_id": data["result"]["message_id"]}
        return {"ok": False, "error": data.get("description", "unknown API error")}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def send_alert_tool(parameters: dict, player=None, speak=None) -> str:
    """Action entry point for the registry (same signature as other tools).

    Params: message (required), parse_mode (optional).
    """
    params = parameters or {}
    text = params.get("message") or params.get("text") or ""
    if not text:
        return "No message provided for the Telegram alert."
    result = send_message(text, parse_mode=params.get("parse_mode", "Markdown"))
    if result["ok"]:
        out = f"Alert sent to Telegram (msg #{result['message_id']})."
    else:
        out = f"Telegram alert failed: {result['error']}"
    try:
        if player and hasattr(player, "write_log"):
            player.write_log(f"TG: {out[:60]}")
    except Exception:
        pass
    return out
