"""
core/scheduler.py — Lightweight daemon that runs Eva on a timer.

Every N seconds (default 900 = 15 min), asks Eva for a live gold read via the
role dispatch path. If the price moved more than a configurable threshold since
the last check, sends a Telegram alert. Every run is recorded in the audit trail
so the dashboard shows the daemon's heartbeat.

Design rules:
- Runs in a background thread, started from main.py after the UI is up.
- Uses the same registry/role_agent/audit stack as live dispatch (no separate path).
- Failure-isolated: a failed run logs an error and schedules the next one.
- Stoppable: call scheduler.stop() on shutdown.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Callable, Any

from core.audit import AuditLog
from core.tradingview import get_analysis
from core.telegram import send_message


class GoldWatcher:
    """Periodic gold-price monitor with Telegram alerts."""

    def __init__(
        self,
        audit: AuditLog,
        interval_seconds: int = 900,
        alert_threshold_pct: float = 0.3,
        run_role_fn: Callable | None = None,
    ):
        self.audit = audit
        self.interval = interval_seconds
        self.threshold = alert_threshold_pct
        self.run_role_fn = run_role_fn  # optional: full role dispatch (Eva)
        self._last_price: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="gold-watcher")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                did = self.audit.record_decision(
                    "daemon", "gold_check", status="pending",
                    detail="scheduler tick crashed",
                )
                self.audit.update_decision(did, status="failed", error=str(e))
            self._stop.wait(self.interval)

    def _tick(self):
        """One check cycle: get price, compare, maybe alert, always log."""
        # Quick price via tradingview_ta (no role agent needed for the check)
        result = get_analysis("gold", "15m")

        if not result.get("ok"):
            did = self.audit.record_decision(
                "daemon", "gold_check", target_role="eva", status="pending",
            )
            self.audit.update_decision(did, status="failed", error=result.get("text", "unknown"))
            return

        price = result.get("close")
        rec = result.get("recommendation", "")
        text = result.get("text", "")

        # Record the heartbeat
        did = self.audit.record_decision(
            "daemon", "gold_check", target_role="eva",
            task=f"gold={price} signal={rec}", status="pending",
        )
        self.audit.update_decision(did, status="executed", result=text)

        # Price-move alert
        if price and self._last_price:
            pct = abs(price - self._last_price) / self._last_price * 100
            if pct >= self.threshold:
                direction = "UP" if price > self._last_price else "DOWN"
                alert = (
                    f"*Gold Alert* {direction} {pct:.1f}%\n"
                    f"Was: ${self._last_price:.2f} -> Now: ${price:.2f}\n"
                    f"Signal: {rec}\n"
                    f"{text}"
                )
                tg = send_message(alert)
                self.audit.record_tool_call(
                    "send_alert", decision_id=did, actor="daemon",
                    args={"message": alert[:200]},
                    result="sent" if tg.get("ok") else tg.get("error", ""),
                    error="" if tg.get("ok") else tg.get("error", ""),
                )

        # Optionally run full Eva analysis (richer, but heavier on CPU)
        if self.run_role_fn and self._should_run_full_analysis(price, rec):
            try:
                eva_result = self.run_role_fn("eva", f"Gold is at {price}, signal {rec}. Give a quick technical read.")
                self.audit.record_tool_call(
                    "eva_daemon_analysis", decision_id=did, actor="daemon",
                    args={"price": price, "signal": rec},
                    result=str(eva_result)[:500] if eva_result else "",
                )
            except Exception:
                pass  # Eva failure is non-critical for the daemon

        self._last_price = price

    def _should_run_full_analysis(self, price: float | None, rec: str) -> bool:
        """Only run the expensive Eva analysis when something interesting happens."""
        if not self._last_price or not price:
            return False
        pct = abs(price - self._last_price) / self._last_price * 100
        # Run full analysis on big moves or strong signals
        return pct >= self.threshold or rec in ("STRONG_BUY", "STRONG_SELL")

    def status(self) -> dict:
        return {
            "running": self.running,
            "interval": self.interval,
            "threshold": self.threshold,
            "last_price": self._last_price,
        }
