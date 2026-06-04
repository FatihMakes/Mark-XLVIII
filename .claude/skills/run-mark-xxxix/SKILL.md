---
name: run-mark-xxxix
description: Launch and drive MARK XXXIX voice AI assistant with live dashboard. Handles GUI automation, screenshots, and smoke tests.
skills:
  - PyQt6 GUI testing
  - Python project launching
  - Cross-platform desktop automation
  - Headless X11 testing (Linux)
---

# Run MARK XXXIX

MARK XXXIX is a real-time voice AI assistant (Gemini 2.5 Flash Native Audio) with a PyQt6 GUI, 10 specialist agents, and a 24/7 background daemon. This skill launches the app on Windows/macOS/Linux (headless on Linux via Xvfb), provides programmatic control via a driver harness, and captures screenshots for visual verification.

## Prerequisites

**Ubuntu/Debian (Linux headless):**
```bash
apt-get install -y python3 python3-pip python3-venv xvfb imagemagick scrot libqt6gui6
```

**macOS:**
```bash
# PyQt6 and audio libs are in requirements.txt
# XQuartz (if needed): brew install xquartz
```

**Windows 10/11:**
```
# Just Python 3.11+ and requirements.txt
```

## Build

### 1. Install Python Dependencies

```bash
cd <project_root>
python driver.py setup
```

This installs everything from `requirements.txt`, including:
- `PyQt6` (GUI framework)
- `google-genai` (Gemini API)
- `sounddevice`, `numpy` (audio processing)
- `yfinance`, `pandas` (market data)
- `playwright` (web automation for agents)
- 50+ specialist libraries for agents, scraping, charting, etc.

**First-time note:** Playwright requires `playwright install` (done by setup). Some OS-specific packages (`libqt6*` on Linux) may need `apt-get` if missing; the setup will warn you.

### 2. Verify Configuration

Ensure `config/api_keys.json` exists:
```json
{
  "gemini_api_key": "your_free_gemini_api_key_here"
}
```

Get a free Gemini API key at https://aistudio.google.com/app/apikey.

## Run (Agent Path)

The driver harness provides programmatic control for CI/testing:

```bash
# Launch the app (on Linux: starts Xvfb virtual display automatically)
python .claude/skills/run-mark-xxxix/driver.py launch

# In another terminal, while app is running:
# Run smoke tests (process alive, modules load, config valid)
python .claude/skills/run-mark-xxxix/driver.py test

# Capture screenshot (outputs to .claude/skills/run-mark-xxxix/screenshot.png)
python .claude/skills/run-mark-xxxix/driver.py screenshot /path/to/out.png
```

**Driver commands:**
- `setup` — Install dependencies
- `launch` — Start the app (runs forever, Ctrl+C to stop; auto-starts Xvfb on Linux)
- `test` — Smoke tests: process alive, modules importable, API config valid
- `screenshot` — Capture window to PNG

**Stdout/stderr:** The driver logs to stdout; app output goes to the running process. On Linux headless, GUI renders to the Xvfb virtual framebuffer (not visible, but screenshots capture it).

## Run (Human Path)

If you just want to use the app interactively:

```bash
cd <project_root>
python main.py
```

This opens a PyQt6 window on Windows/macOS. On Linux, you need an X server (use Xvfb + remote display, or a desktop environment).

## Test

Smoke tests verify core functionality without needing Gemini calls:

```bash
python .claude/skills/run-mark-xxxix/driver.py test
```

Tests:
1. **Process alive** — App didn't crash on startup
2. **API config** — Gemini key is in `config/api_keys.json`
3. **Module imports** — Core modules (`ui`, `TradingAgent`, `DataBridge`) load without errors

All three passing = app is launchable.

## Gotchas

### 1. Xvfb and Virtual Display (Linux)

**Problem:** `PyQt6: Could not connect to display` on Linux.

**Fix:** The driver auto-starts Xvfb on `DISPLAY=:99`. If you're running outside the driver:
```bash
export DISPLAY=:99
Xvfb :99 -screen 0 1280x720x24 &
python main.py
```

If Xvfb isn't installed: `apt-get install -y xvfb`

### 2. Protobuf C Extension Metaclass (Python 3.14)

**Problem:** `ImportError: cannot import name '_message'` or metaclass conflicts on Python 3.14.

**Workaround:** Already patched in `main.py` lines ~1-30. The patch stubs `sys.modules['google.protobuf.message']` before other imports. **Never remove this block** — it's how Python 3.14 gets around the protobuf C extension issue.

**Note:** Python 3.11–3.13 don't need the patch; it's harmless if present.

### 3. Audio Input (Microphone)

**Problem:** `sounddevice.PortAudioError` if no audio device.

**Fix:** Linux headless containers have no audio. The app will error when you try voice input. Workaround for testing: set a dummy audio device or test via keyboard input instead.

### 4. Qt Threading (Dashboard Widget Creation)

**Critical:** All PyQt6 widget creation MUST happen on the main thread.

- `ui/dashboard.py` uses a Queue + QTimer (100ms drain) so background threads can safely call `open_dashboard()` without race conditions.
- If you see widget crashes in multi-threaded code, check that `init_dashboard_controller()` was called in `main()` before `QApplication.exec()`.

### 5. yfinance Symbol Mapping

The app uses non-standard symbols for some assets:
- Gold → `GC=F` (not `XAU-USD`)
- Oil → `CL=F` (not `OIL`)
- EUR-USD → `EURUSD=X`
- Bitcoin → `BTC-USD`

Always use these in trading/chart queries, or you'll get "symbol not found" errors.

### 6. Memory Leaks in Multi-Agent Runs

**Problem:** Running `AutonomousAgent` or parallel agent orchestration can accumulate memory over long sessions.

**Cause:** Agent instances hold references to Gemini sessions and data frames. The daemon's default jobs (morning briefing, news refresh, price monitor) run indefinitely.

**Workaround:** Restart the app every 8 hours, or kill the daemon if you're just testing agents.

### 7. API Rate Limits

**Problem:** Gemini API returns 429 errors after ~2000 quick queries.

**Fix:** Free tier has rate limits. Space out queries or use a paid API key. Agents cache responses in `memory/` so repeated queries are fast.

### 8. Screenshot Capture on Windows/macOS

**Problem:** `driver.py screenshot` not implemented for Windows/macOS.

**Workaround:** Use OS-native tools:
- Windows: `powershell "[System.Windows.Forms.SendKeys]::SendWait('%{PRTSC}')"` (Print Screen)
- macOS: `screencapture -x screenshot.png`
- Or just manually screenshot the window.

## Troubleshooting

### App won't start: `ModuleNotFoundError: No module named 'X'`

**Fix:** A dependency is missing.
```bash
pip install <module_name>
# or re-run setup
python .claude/skills/run-mark-xxxix/driver.py setup
```

Check which libraries you're missing by looking at the import at the top of `main.py` or `agents/`.

### App crashes on startup: `Segmentation Fault` or `QXcbConnection: Could not connect to display`

**On Linux:**
```bash
export DISPLAY=:99
Xvfb :99 -screen 0 1280x720x24 &
python main.py
```

**On Windows/macOS:** This usually means a dependency is corrupted. Reinstall `PyQt6`:
```bash
pip install --force-reinstall PyQt6 PyQt6-Qt6 PyQt6_sip
```

### API key error: `Invalid API key` or `AuthenticationError`

**Fix:** Verify `config/api_keys.json`:
```bash
cat config/api_keys.json
```

Key must be a valid Gemini API key (get one free at https://aistudio.google.com/app/apikey).

If you don't want to create the file, set via environment:
```bash
export GEMINI_API_KEY=your_key_here
python main.py
```

(app will read from env if config file is missing)

### Dashboard window is blank or not rendering

**Cause:** X11 or Qt rendering issue on headless systems.

**Note:** Headless mode (Xvfb) renders to a virtual framebuffer, not your screen. Screenshots will work, but you can't see the window live. For interactive use, you need an actual X server or a desktop environment.

**Workaround for testing:** Use the driver's smoke tests, which don't require visual rendering:
```bash
python .claude/skills/run-mark-xxxix/driver.py test
```

### Daemon (24/7 background scheduler) crashes or consumes memory

**Cause:** Long-running daemon with agents holding resources.

**Fix:** The daemon is optional. If you're just testing the main UI:
1. Comment out `daemon_start()` in `main.py` (around line 500)
2. Or kill `MarkDaemon` from task manager after app starts

### Agent fails: `yfinance returned empty DataFrame` or scraper returns no data

**Cause:** Data source unavailable (API rate limit, network, or market closed).

**Fix:** Agents have fallback chains. Check `agents/trading_agent.py` — it tries `yfinance` first, then `cloudscraper`, then returns cached data. If all fail, the agent returns an error message (which Jarvis will voice).

For testing: use cached data or mock responses instead of live queries.

---

## Architecture Notes

This is a complex multi-agent system. Key components:

| Component | File | Purpose |
|---|---|---|
| **Voice I/O** | `main.py` | Gemini live audio session, tool declarations, response handling |
| **GUI** | `ui/__init__.py` | PyQt6 interface, log window, controls |
| **Dashboard** | `ui/dashboard.py` | Live prices, charts, agents, daemon, news, Telegram |
| **Daemon** | `core/daemon.py` | 24/7 scheduler (5 default jobs) |
| **Data Cache** | `core/data_bridge.py` | Thread-safe in-memory store: prices, agent states, activity log |
| **Agents** | `agents/` | 10 specialist agents (trading, news, weather, autonomous, etc.) |
| **Tools** | `actions/` | System control, file ops, web search, app launcher, etc. |
| **Memory** | `memory/` | Persistent agent logs and conversation history |

For a future agent reading this skill to **develop** MARK XXXIX further, understand that:
- Adding a new agent: Inherit from `BaseAgent`, add to `agents/`, wire into `actions/mark_agents.py`
- Adding a new tool: Create in `actions/`, add schema to `main.py`'s tool declarations, implement handler
- GUI changes: Modify `ui/__init__.py` or `ui/dashboard.py`; ensure all widget creation is on main thread
- Daemon jobs: Add to `core/daemon.py` (e.g., `"MyJob": {"schedule": "0 9 * * *", ...}`)

---

## Quick Links

- **API Key:** https://aistudio.google.com/app/apikey
- **Gemini Docs:** https://ai.google.dev/
- **PyQt6 Docs:** https://www.riverbankcomputing.com/static/Docs/PyQt6/
- **Open-Meteo Weather API:** https://open-meteo.com/
- **yfinance Docs:** https://yfinance.readthedocs.io/
