# ⚙️ MARK XLVIII (48)
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://www.youtube.com/@FatihMakes)**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supports Windows, macOS, and Linux. Built on the Gemini Live API for native audio streaming, delivering zero subscriptions and total digital autonomy.

---

## ✨ Overview

MARK XLVIII is a direct evolution of Mark XLVII — sharper, faster, and more natural to talk to. This build focused entirely on removing every friction point: the silence while JARVIS "thinks," the awkward double-responses, the interrupts that took four seconds to land, the news results that linked to homepages instead of articles. Everything that made the experience feel like software instead of an assistant has been addressed.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language via Gemini Live API |
| 🖥️ System Control | Launch apps, adjust volume/brightness, WiFi, shortcuts, power — all by voice |
| 🧩 Autonomous Tasks | High-level planning for complex multi-step goals via agent mode |
| 👁️ Visual Awareness | Real-time screen capture and webcam vision piped into your main Gemini session |
| 🧠 Persistent Memory | Deeply remembers projects, preferences, and personal context across sessions |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |
| 🌅 Morning Briefing | On first boot: greets you, reads the time, fetches live news headlines, and checks weather |
| 🔔 Proactive Check-ins | After 15 minutes of silence JARVIS checks context and offers something genuinely useful — no hardcoded rules, Gemini decides |
| 📊 Hardware Monitoring | Continuous CPU, RAM, GPU and temperature telemetry with localized voice alerts when thresholds are breached |
| 🌤️ Weather Report | Live weather data for your city, personalized from memory |
| 🗺️ Dynamic Content Panel | Scrollable display layer beneath the HUD that renders web results, news, and search data with timestamps |
| 🔍 Multi-Mode Web Search | `news` / `research` / `price` / `compare` / `search` — Gemini Grounded first, DDG fallback |
| ⏰ Smart Reminders | OS-native scheduled notifications (Windows Task Scheduler / macOS LaunchAgent / Linux systemd) |
| ✈️ Flight Finder | Live flight price and availability lookup |
| 🎮 Game Updater | Checks and triggers game updates on demand |
| 📂 File Processor | Read, summarize, and answer questions about local files |
| 💻 Code Helper | Inline code review, debugging, and generation |
| 🌐 Browser Control | Open URLs, navigate tabs, and interact with the browser by voice |
| 📨 Send Message | Compose and send messages through integrated messaging apps |
| 🎬 YouTube Control | Search, play, and control YouTube playback by voice |
| 🖱️ Desktop Control | Taskbar, window management, and desktop-level operations |
| 🧑‍💻 Silent Language Memory | Detects spoken language on first use and saves it silently — all future sessions and briefings adapt automatically |

---

## 🆕 What's New in XLVIII

### ✋ Instant Interrupt — ESC or Button
Press **Escape** or click the `INTERRUPT` button to cut JARVIS off mid-sentence and return to listening. Previously, cancelling a response required waiting for the full audio buffer to drain — sometimes four seconds. In Mark XLVIII, audio is split into ~50 ms chunks (2400 bytes each) so the interrupt fires within one slice. The interrupt drains the audio queue, sets a flag, and clears the turn — listening resumes in under 100 ms.

### 👁️ Immediate Vision Acknowledgment
When you ask JARVIS to look at your screen or camera, it no longer goes silent while processing. The tool now instructs Gemini to immediately say a natural sentence ("Looking at your screen now, sir" / "Ekrana bakıyorum efendim") while the image capture runs. The actual analysis follows as a second response. No more awkward silence.

### 📰 Parallel News Search — First Result Wins
News queries now run **Gemini Grounded Search and DuckDuckGo news simultaneously** in two daemon threads. Whichever delivers a valid result first wins; the other is silently discarded. Previously, a Gemini 503 error would stall the search for several seconds before falling back to DDG. Now the fallback happens in parallel — total news fetch time drops to whichever backend is fastest at that moment.

### 🗞️ Real News Articles (Not Homepages)
DDG news search was previously using `ddgs.text()`, which returned website homepage URLs for news queries. Mark XLVIII switches to `ddgs.news()`, which returns actual article URLs, titles, snippets, and source names — exactly what you want in a news briefing.

### 🌅 Two-Phase Startup Briefing — Runs Concurrently
The startup briefing now sends Phase 2 (news fetch) while Phase 1 audio (the greeting) is still playing. Previously, Phase 2 waited for Phase 1 to fully complete. The 1.5-second overlap means the news headline is ready by the time JARVIS finishes saying "Good morning."

### 🔁 Smarter Reconnection — Exponential Backoff
Network timeouts now use exponential backoff: 3s → 6s → 12s → 60s (capped). Each retry shows a Turkish-language status message in the UI ("Bağlantı kurulamadı — Xs sonra tekrar deneniyor"). Previously, a dropped connection would loop tightly and show no useful information.

### 🛡️ Vision Cooldown & Echo Guard
Screen capture is guarded against echo loops. If JARVIS speaks about the screen and the microphone picks up its own voice, a secondary `screen_process` call can be triggered. Mark XLVIII blocks duplicate calls with a 4-second cooldown and a `_vision_busy` flag. Both are fully reset when a new session connects — fixing a bug where the cooldown would persist across reconnects and block legitimate requests.

### 🌐 Language-Aware Address — Never Mixed
The system prompt now enforces: **Turkish → efendim**, **English → sir**, never mixed. Mark XLVII's prompt said "Always call sir to user" which caused JARVIS to say "sir" mid-Turkish sentence. Fixed.

### 🪟 Zero Terminal Windows
A subprocess monkey-patch at startup sets `CREATE_NO_WINDOW` on every child process launched by the app. No PowerShell, no CMD, no terminal flash — ever. Applies to all actions including reminders, system commands, and scheduler calls.

### 🔄 Session State Isolation
All transient vision and interrupt flags (`_pending_vision`, `_vision_busy`, `_vision_cam_active`, `_vision_close_pending`, `_interrupted`) are fully reset whenever a new Gemini session connects. Previously, state from a crashed session could carry over and leave JARVIS in a broken state until restart.

---

## ⚡ Quick Start

```bash
git clone https://github.com/FatihMakes/Mark-XLVIII.git
cd Mark-XLVIII
pip install -r requirements.txt
python main.py
```

> ⚠️ **Installation Note:** Some OS-specific dependencies are not bundled in `requirements.txt` to keep the repo lightweight. If you hit a `ModuleNotFoundError`, install the missing package with `pip install <module_name>`.

---

## 📋 Requirements

| Requirement | Details |
| --- | --- |
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key (`config/api_keys.json`) |

---

## 🗂️ Project Structure

```
Mark XLVIII/
├── main.py                  # Core loop — Gemini Live session, audio I/O, tool dispatch
├── ui.py                    # PyQt6 HUD — waveform, log panel, interrupt button, camera feed
├── setup.py                 # First-run configuration wizard
├── actions/
│   ├── web_search.py        # Gemini + DDG parallel search (news, research, price, compare)
│   ├── screen_processor.py  # Screen capture & webcam vision via Gemini Live
│   ├── reminder.py          # OS-native scheduled notifications
│   ├── system_monitor.py    # CPU / RAM / GPU / temperature telemetry
│   ├── computer_settings.py # Volume, brightness, WiFi, power
│   ├── computer_control.py  # Keyboard shortcuts, mouse, window management
│   ├── open_app.py          # Application launcher
│   ├── browser_control.py   # Web browser control
│   ├── file_controller.py   # File system operations
│   ├── file_processor.py    # Document reading and summarization
│   ├── send_message.py      # Messaging integration
│   ├── weather_report.py    # Live weather data
│   ├── flight_finder.py     # Flight search
│   ├── youtube_video.py     # YouTube playback control
│   ├── game_updater.py      # Game update management
│   ├── code_helper.py       # Code review and generation
│   ├── dev_agent.py         # Developer task agent
│   ├── desktop.py           # Desktop and taskbar control
│   └── proactive.py        # Proactive silence-break suggestions
├── memory/                  # Persistent key-value memory store
├── core/
│   └── prompt.txt           # JARVIS personality and tool-routing rules
└── config/
    └── api_keys.json        # API key and system configuration
```

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Connect with the Creator

Engineered by a developer building a real-world JARVIS-style assistant.
⭐ **Star the repository to support the journey to Mark 100.**

| Platform | Link |
| --- | --- |
| YouTube | [@FatihMakes](https://www.youtube.com/@FatihMakes) |
| Instagram | [@fatihmakes](https://www.instagram.com/fatihmakes) |
