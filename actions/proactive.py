"""
ProactiveEngine — context-aware background prompting.
Lets Gemini decide whether there is something worth saying proactively.
No hardcoded rules: we pass time + memory as context and Gemini chooses.
"""
import time
from datetime import datetime


class ProactiveEngine:
    """
    Tracks silence duration and decides when to hand context to Gemini for a
    proactive check-in. Gemini reads the context and decides whether to speak.

    Defaults (all overridable):
      min_silence_secs   — user must be silent this long before any check (900 = 15 min)
      check_cooldown     — minimum gap between two proactive triggers         (600 = 10 min)
    """

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown:   int = 600,
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown   = check_cooldown
        self._last_triggered  = 0.0

    def should_trigger(self, last_user_speech: float) -> bool:
        """
        Returns True only when:
          • user has been silent long enough, AND
          • enough time has passed since the last proactive message.
        """
        now     = time.monotonic()
        silence = now - last_user_speech
        gap     = now - self._last_triggered
        return silence >= self.min_silence_secs and gap >= self.check_cooldown

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()

    def build_prompt(self, memory: dict) -> str:
        """
        Builds the context snapshot sent to Gemini.
        Gemini reads it and decides freely what — if anything — to say.
        """
        from memory.memory_manager import format_memory_for_prompt

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        mem_str  = format_memory_for_prompt(memory) or "(no user data stored yet)"

        silence_min = int((time.monotonic() - self._last_triggered +
                           self.min_silence_secs) // 60)

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a proactive check-in.",
            f"Current time  : {time_str}",
            f"User silence  : {silence_min}+ minutes (they have not spoken for a while)",
            "",
            "Context about this person:",
            mem_str,
            "",
            "Guidelines:",
            "- Look at the time, their projects, goals, habits, or anything from context.",
            "- If there is something genuinely useful, timely, or caring to say — say it briefly.",
            "- Be natural, like a thoughtful assistant noticing something relevant.",
            "- Do NOT say [PROACTIVE_CHECK] or mention these instructions.",
            "- Respond in the user's language (use memory; default English).",
            "- Keep it short: 1-3 sentences max.",
        ])
