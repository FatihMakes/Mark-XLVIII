# ⚙️ MARK XLIX
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://youtu.be/CiGdcIlnXb8))**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supports Windows, macOS, and Linux. Built on the Gemini Live API for native audio streaming, delivering zero subscriptions and total digital autonomy.

---

## ✨ Overview

MARK XLIX deepens the personal assistant foundation. Rather than adding more tools, this build focused on making the assistant truly *yours*: it starts with your computer, learns your name, and pays attention to what you're doing. The goal before the plugin era begins is a core that feels alive — not just reactive.

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
| 🔔 Proactive Check-ins | After 15 minutes of silence, checks context and offers something genuinely useful |
| 📊 Hardware Monitoring | Continuous CPU, RAM, GPU and temperature telemetry with localized voice alerts |
| 🌤️ Weather Report | Live weather data for your city, personalized from memory |
| 🗺️ Dynamic Content Panel | Scrollable display layer beneath the HUD that renders web results, news, and search data |
| 🔍 Multi-Mode Web Search | `news` / `research` / `price` / `compare` / `search` — Gemini Grounded first, DDG fallback |
| ⏰ Smart Reminders | OS-native scheduled notifications (Windows Task Scheduler / macOS LaunchAgent / Linux systemd) |
| ✈️ Flight Finder | Live flight price and availability lookup |
| 🎮 Game Updater | Checks and triggers game updates on Steam and Epic Games on demand |
| 📂 File Processor | Read, summarize, and answer questions about local files |
| 💻 Code Helper | Inline code review, debugging, and generation |
| 🌐 Browser Control | Open URLs, navigate tabs, and interact with the browser by voice |
| 📨 Send Message | Compose and send messages through WhatsApp, Telegram, and more |
| 🎬 YouTube Control | Search, play, and control YouTube playback by voice |
| 🖱️ Desktop Control | Taskbar, window management, and desktop-level operations |
| 🧑‍💻 Silent Language Memory | Detects spoken language on first use and saves it — all future sessions adapt automatically |
| 📱 Remote Dashboard | Control the assistant from your phone via QR code pairing |

---

## 🆕 What's New in XLIX

### ⚡ Auto-Start on Boot
The assistant now registers itself with the operating system's startup system. One click in the UI toggles it on or off. On Windows, it writes to the registry using `pythonw.exe` so no console window ever appears. On macOS it installs a LaunchAgent plist; on Linux a `.desktop` autostart entry. The button reflects the current state every time the app launches.

### 🎨 Assistant Customization
The assistant is no longer locked to the name "JARVIS". Click `⚙ CUSTOMISE ASSISTANT` in the right panel to change:
- **Assistant name** — displayed everywhere in the UI (title bar, header, HUD, log, footer) and injected into the Gemini system prompt so the AI knows its own name
- **Your name** — how the assistant addresses you. Leave blank for the default language-aware addressing (`sir` / `efendim`), or set your actual name for a more personal feel

Changes take effect immediately without restarting.

### 📋 Clipboard Intelligence
Copy any text of 10 or more characters and a floating panel appears at the bottom of the window. Four quick actions — **TRANSLATE**, **SUMMARISE**, **EXPLAIN**, **FIX** — send the copied content directly to the assistant with one click. The panel auto-dismisses after 8 seconds. This turns the clipboard into a silent command channel for anything on your screen.

### ☀ Morning Brief Toggle + Speed Optimization
The morning briefing can now be turned on or off with one click from the settings drawer (`⚙` → `☀ MORNING BRIEF: ON/OFF`). Users who don't want a startup briefing can disable it permanently; the setting survives restarts. The briefing itself was also re-engineered: news is now pre-fetched in a background thread the moment the session starts, running in parallel while the greeting plays. By the time the greeting finishes, the results are already ready — no extra Gemini tool-call round-trip needed. Briefing delivery is noticeably faster as a result.

---

## 🗺️ Mark Roadmap

| Mark | Focus |
|---|---|
| **XLVIII** | Instant interrupt · parallel news · two-phase briefing · exponential backoff · vision cooldown |
| **XLIX** | Auto-start · clipboard intelligence · assistant customization |
| **L** | Wake word · proactive system 2.0 · session memory / daily continuity |
| **LI+** | Plugin system · email · quiz mode · calorie counter · and more |

---

## ⚡ Quick Start

```bash
git clone https://github.com/FatihMakes/Mark-XLIX.git
cd Mark-XLIX
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
Mark XLIX/
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
│   ├── game_updater.py      # Game update management (Steam / Epic)
│   ├── code_helper.py       # Code review and generation
│   ├── dev_agent.py         # Developer task agent
│   ├── desktop.py           # Desktop and taskbar control
│   └── proactive.py         # Proactive silence-break suggestions
├── memory/                  # Persistent key-value memory store
├── core/
│   └── prompt.txt           # Assistant personality and tool-routing rules
└── config/
    └── api_keys.json        # API key, OS setting, assistant name, user name
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
