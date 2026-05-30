import asyncio
import array
import contextlib
import math
import re
import signal
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from wakeword import WakeWordDetector
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.music_player      import get_music_player, music_player


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
APP_CONFIG_PATH = BASE_DIR / "config" / "config.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024
DEFAULT_CONVERSATION_IDLE_SLEEP_SECONDS = 60
DEFAULT_WAKE_WORD_MODEL = "models/nee_how__ahh_niu.onnx"
OUTPUT_SILENCE_RMS_THRESHOLD = 200
READY_CHIME_SAMPLE_RATE = 24000
READY_CHIME_DURATION_SECONDS = 0.18
READY_CHIME_FREQUENCY_HZ = 880
READY_CHIME_VOLUME = 0.22
MUSIC_WAKE_GRACE_SECONDS = 3.0

def _load_app_config() -> dict:
    config = {
        "conversation_idle_sleep_seconds": DEFAULT_CONVERSATION_IDLE_SLEEP_SECONDS,
        "wake_word_model": DEFAULT_WAKE_WORD_MODEL,
    }
    try:
        with open(APP_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return config
    except Exception as e:
        print(f"[JARVIS] Failed to load app config: {e}")
        return config

    if isinstance(data, dict):
        config.update({k: v for k, v in data.items() if k in config})
    return config

def _resolve_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return BASE_DIR / path

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

def _is_silent_pcm16(data: bytes, threshold: int = OUTPUT_SILENCE_RMS_THRESHOLD) -> bool:
    usable_len = len(data) - (len(data) % 2)
    if usable_len <= 0:
        return True

    samples = array.array("h")
    samples.frombytes(data[:usable_len])
    if sys.byteorder == "big":
        samples.byteswap()
    if not samples:
        return True

    limit = threshold * threshold * len(samples)
    return sum(sample * sample for sample in samples) <= limit

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "music_player",
        "description": (
            "Searches online music by keyword, downloads the selected song, plays it locally, "
            "and controls music playback. Use for ALL music/song requests: play music, search songs, "
            "play a random cached local song, play the cached local library in random order, "
            "pause music, resume music, stop music, toggle playback, seek within a song, get lyrics, "
            "or check music status. Do NOT use youtube_video, web_search, or open_app for music playback."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "search_play | search | play | play_local | play_local_library | pause | resume | toggle | stop | seek | lyrics | status (default: search_play). Use play_local for 播放本地歌曲 without a song name. Use play_local_library for 播放本地曲库 without a song name."
                },
                "query": {
                    "type": "STRING",
                    "description": "Song/music keyword, song name, artist, or search phrase"
                },
                "choice": {
                    "type": "INTEGER",
                    "description": "Selected search result index, starting at 1 (default: 1)"
                },
                "position_seconds": {
                    "type": "NUMBER",
                    "description": "Target playback position in seconds for seek"
                },
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": (
            "Ends the current voice conversation and returns the assistant to sleep mode. "
            "Call this only when the user explicitly gives an exit, quit, close, "
            "stop, goodbye, or stop-listening command for Jarvis. "
            "The application keeps running and waits for the wake word again. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._wake_audio_queue = None
        self._wake_detector = None
        self._wake_event: asyncio.Event | None = None
        self._sleep_event: asyncio.Event | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._conversation_active = False
        self._conversation_starting = False
        self._music_sleep_active = False
        self._music_sleep_requested = False
        self._wake_after_music = False
        self._music_sleep_started_at = 0.0
        self._startup_audio_buffer = []
        self._pending_text_commands: list[str] = []
        self._pending_text_lock = threading.Lock()
        self._app_config = _load_app_config()
        self._conversation_idle_sleep_seconds = self._read_idle_sleep_seconds()
        self._wake_word_model_path = _resolve_path(
            str(self._app_config.get("wake_word_model") or DEFAULT_WAKE_WORD_MODEL)
        )
        self._last_conversation_activity = 0.0
        self._sleep_after_turn = False
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self._tool_running = False
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None

    def request_shutdown(self):
        if not self._loop:
            return

        def _set_shutdown():
            if self._shutdown_event:
                self._shutdown_event.set()
            if self._sleep_event:
                self._sleep_event.set()
            if self._wake_event:
                self._wake_event.set()

        self._loop.call_soon_threadsafe(_set_shutdown)

    def _read_idle_sleep_seconds(self) -> float:
        value = self._app_config.get("conversation_idle_sleep_seconds")
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return float(DEFAULT_CONVERSATION_IDLE_SLEEP_SECONDS)
        return max(0.0, seconds)

    def _mark_conversation_activity(self):
        self._last_conversation_activity = asyncio.get_running_loop().time()

    def _music_is_playing(self) -> bool:
        try:
            status = get_music_player().status()
        except Exception:
            return False
        return bool(status.get("playing") and not status.get("paused"))

    def _begin_music_sleep(self):
        if not self._music_is_playing():
            return
        if not self._music_sleep_active:
            self._music_sleep_active = True
            self.ui.write_log("SYS: Music playback started. Sleeping until playback ends or wake word is detected.")
            self.ui.set_state("SLEEPING")
        self._music_sleep_started_at = asyncio.get_running_loop().time()
        self._music_sleep_requested = True
        self._wake_after_music = False
        self._drain_wake_audio_queue()

    def _wake_from_music_sleep(self):
        if not self._music_sleep_active:
            return
        try:
            get_music_player().pause()
        except Exception as e:
            self.ui.write_log(f"ERR: Failed to pause music on wake word - {str(e)[:120]}")
        self._music_sleep_active = False
        self._music_sleep_requested = False
        self._wake_after_music = False
        self._music_sleep_started_at = 0.0
        self.ui.write_log("SYS: Wake word detected during music playback. Music paused for conversation.")

    def _finish_music_sleep(self):
        if not self._music_sleep_active:
            return
        conversation_is_stopping = bool(self._sleep_event and self._sleep_event.is_set())
        self._music_sleep_active = False
        self._music_sleep_requested = False
        self._music_sleep_started_at = 0.0
        self._drain_wake_audio_queue()
        self.ui.write_log("SYS: Music playback ended. Returning to conversation mode.")
        if self._conversation_active and not conversation_is_stopping:
            self._wake_after_music = False
            self.ui.set_state("LISTENING" if not self.ui.muted else "SLEEPING")
            return

        self._wake_after_music = True
        self.ui.set_state("THINKING")
        if not self._conversation_active and not self._conversation_starting:
            if self._wake_event and not self._wake_event.is_set():
                self._wake_event.set()

    async def _watch_music_sleep(self):
        while True:
            if self._music_sleep_active and not self._music_is_playing():
                self._finish_music_sleep()
            await asyncio.sleep(0.25)

    def _activate_music_sleep_after_tool_response(self):
        if not self._music_sleep_requested:
            return
        self._music_sleep_requested = False
        if self._music_sleep_active and self._music_is_playing() and self._sleep_event:
            self._sleep_event.set()
        else:
            self._finish_music_sleep()

    async def _watch_conversation_idle(self):
        timeout = self._conversation_idle_sleep_seconds
        if timeout <= 0:
            return

        while True:
            elapsed = asyncio.get_running_loop().time() - self._last_conversation_activity
            remaining = timeout - elapsed
            if remaining <= 0:
                self.ui.write_log("SYS: No conversation activity. Returning to sleep mode.")
                if self._sleep_event:
                    self._sleep_event.set()
                return
            await asyncio.sleep(min(remaining, 1.0))

    def _on_text_command(self, text: str):
        text = text.strip()
        if not text:
            return

        if not self._loop:
            self._queue_text_command(text)
            return

        def _handle_text_command():
            if self.session and self._conversation_active:
                asyncio.create_task(self._send_text_command(text))
                return

            if self._music_sleep_active:
                self._wake_from_music_sleep()

            self._queue_text_command(text)
            if self._conversation_starting:
                self.ui.write_log("SYS: Text command queued while JARVIS wakes.")
                return

            self._conversation_starting = True
            self.ui.set_state("THINKING")
            self.ui.write_log("SYS: Text command received. Waking JARVIS.")
            if self._wake_event and not self._wake_event.is_set():
                self._wake_event.set()

        self._loop.call_soon_threadsafe(_handle_text_command)

    def _queue_text_command(self, text: str):
        with self._pending_text_lock:
            self._pending_text_commands.append(text)

    def _pop_pending_text_commands(self) -> list[str]:
        with self._pending_text_lock:
            commands = self._pending_text_commands
            self._pending_text_commands = []
        return commands

    async def _send_text_command(self, text: str):
        if not self.session:
            self._queue_text_command(text)
            return
        self._mark_conversation_activity()
        await self.session.send_client_content(
            turns={"parts": [{"text": text}]},
            turn_complete=True
        )

    async def _flush_pending_text_commands(self):
        for text in self._pop_pending_text_commands():
            await self._send_text_command(text)

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING" if self._conversation_active else "SLEEPING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _play_ready_chime_sync(self):
        sample_count = int(READY_CHIME_SAMPLE_RATE * READY_CHIME_DURATION_SECONDS)
        amplitude = int(32767 * READY_CHIME_VOLUME)
        samples = array.array("h")
        fade_samples = max(1, int(READY_CHIME_SAMPLE_RATE * 0.025))

        for i in range(sample_count):
            envelope = 1.0
            if i < fade_samples:
                envelope = i / fade_samples
            elif sample_count - i < fade_samples:
                envelope = (sample_count - i) / fade_samples

            value = int(
                amplitude
                * envelope
                * math.sin(2 * math.pi * READY_CHIME_FREQUENCY_HZ * i / READY_CHIME_SAMPLE_RATE)
            )
            samples.append(value)

        with sd.RawOutputStream(
            samplerate=READY_CHIME_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        ) as stream:
            stream.write(samples.tobytes())

    async def _play_ready_chime(self):
        self.set_speaking(True)
        try:
            await asyncio.to_thread(self._play_ready_chime_sync)
        except Exception as e:
            print(f"[JARVIS] Ready chime failed: {e}")
        finally:
            self.set_speaking(False)

    def _enqueue_wake_audio(self, data: bytes):
        if not self._wake_audio_queue:
            return
        if self._wake_audio_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._wake_audio_queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self._wake_audio_queue.put_nowait(data)

    def _drain_wake_audio_queue(self) -> int:
        if not self._wake_audio_queue:
            return 0

        drained = 0
        while True:
            try:
                self._wake_audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                return drained
            drained += 1

    async def _reset_wakeword_listening(self):
        drained = self._drain_wake_audio_queue()
        if self._wake_detector:
            await asyncio.to_thread(self._wake_detector.reset)
        if self._wake_event:
            self._wake_event.clear()
        print(f"[JARVIS] 💤 Wake word listener reset ({drained} queued chunks cleared)")

    def _enqueue_realtime_audio(self, data: bytes):
        if not self.out_queue:
            return
        if self.out_queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self.out_queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})

    def _buffer_startup_audio(self, data: bytes):
        self._startup_audio_buffer.append(data)
        max_chunks = 60
        if len(self._startup_audio_buffer) > max_chunks:
            del self._startup_audio_buffer[: len(self._startup_audio_buffer) - max_chunks]

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            session_resumption=types.SessionResumptionConfig(),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "music_player":
                r = await loop.run_in_executor(None, lambda: music_player(parameters=args, response=None, player=self.ui))
                result = {"status": "ok", "result": r or "Done.", "silent": True}
                if self._music_is_playing():
                    self._begin_music_sleep()

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Conversation ended. Returning to sleep mode.")
                self.speak("好的，我先休眠。需要我时请再次呼唤我。")
                self._sleep_after_turn = True
                result = "Conversation ended. Assistant is returning to sleep mode."

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING" if self._conversation_active else "SLEEPING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        response = result if isinstance(result, dict) else {"result": result}
        return types.FunctionResponse(
            id=fc.id, name=name,
            response=response
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(media=msg)

    async def _wait_for_wakeword(self):
        print("[JARVIS] 💤 Wake word detector started")
        self._wake_detector = WakeWordDetector(custom_model=self._wake_word_model_path)

        while True:
            data = await self._wake_audio_queue.get()
            if self._conversation_active or self._conversation_starting or self.ui.muted:
                continue

            detection = await asyncio.to_thread(
                self._wake_detector.process_bytes,
                data,
            )
            if detection and self._wake_event and not self._wake_event.is_set():
                name, confidence = detection
                print(f"[JARVIS] 🟢 Wake word: {name} ({confidence:.2f})")
                self.ui.write_log(f"SYS: Wake word detected ({name}, {confidence:.2f}).")
                if self._music_sleep_active:
                    elapsed = asyncio.get_running_loop().time() - self._music_sleep_started_at
                    if elapsed < MUSIC_WAKE_GRACE_SECONDS:
                        self.ui.write_log("SYS: Ignoring wake word during music startup grace period.")
                        continue
                    self._wake_from_music_sleep()
                if not self._music_sleep_active:
                    self._wake_event.set()

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            data = indata.tobytes()

            if self._conversation_starting and not self.ui.muted:
                loop.call_soon_threadsafe(
                    self._buffer_startup_audio,
                    data,
                )
            elif not self._conversation_active and not self.ui.muted:
                loop.call_soon_threadsafe(
                    self._enqueue_wake_audio,
                    data,
                )

            if (
                self._conversation_active
                and not self._music_sleep_active
                and not jarvis_speaking
                and not self._tool_running
                and not self.ui.muted
                and self.out_queue is not None
            ):
                loop.call_soon_threadsafe(
                    self._enqueue_realtime_audio,
                    data,
                )

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                blocksize=CHUNK_SIZE,
                callback=callback,
            ):
                print("[JARVIS] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():
                    activity_seen = False

                    if response.data:
                        audio_is_silent = _is_silent_pcm16(response.data)
                        activity_seen = activity_seen or not audio_is_silent
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                activity_seen = True
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                activity_seen = True
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

                            if self._sleep_after_turn and self._sleep_event:
                                if self.audio_in_queue.empty():
                                    self._sleep_event.set()

                    if response.tool_call:
                        activity_seen = True
                        fn_responses = []
                        self._tool_running = True
                        try:
                            for fc in response.tool_call.function_calls:
                                print(f"[JARVIS] 📞 {fc.name}")
                                fr = await self._execute_tool(fc)
                                fn_responses.append(fr)
                            await self.session.send_tool_response(
                                function_responses=fn_responses
                            )
                            self._activate_music_sleep_after_tool_response()
                        finally:
                            self._tool_running = False

                    if activity_seen:
                        self._mark_conversation_activity()
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                        if self._sleep_after_turn and self._sleep_event:
                            self._sleep_event.set()
                    continue
                audio_is_silent = _is_silent_pcm16(chunk)
                if audio_is_silent:
                    self.set_speaking(False)
                else:
                    self.set_speaking(True)
                    self._mark_conversation_activity()
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def _run_conversation(self, client):
        print("[JARVIS] 🔌 Connecting...")
        self.ui.set_state("THINKING")
        self._conversation_starting = True
        self._startup_audio_buffer = []
        try:
            config = self._build_config()

            async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
                self.session = session
                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=10)
                self._turn_done_event = asyncio.Event()
                self._sleep_event = asyncio.Event()
                self._sleep_after_turn = False
                self._conversation_active = True
                self._conversation_starting = False
                self._mark_conversation_activity()

                print("[JARVIS] ✅ Connected.")
                await self._play_ready_chime()
                self.ui.set_state("LISTENING")
                self.ui.write_log("SYS: JARVIS awake. Conversation started.")

                for data in self._startup_audio_buffer:
                    self._enqueue_realtime_audio(data)
                self._startup_audio_buffer = []

                tasks = [
                    asyncio.create_task(self._send_realtime()),
                    asyncio.create_task(self._receive_audio()),
                    asyncio.create_task(self._play_audio()),
                ]
                if self._conversation_idle_sleep_seconds > 0:
                    tasks.append(asyncio.create_task(self._watch_conversation_idle()))

                await self._flush_pending_text_commands()

                sleep_task = asyncio.create_task(self._sleep_event.wait())
                shutdown_task = asyncio.create_task(self._shutdown_event.wait())
                tasks.append(sleep_task)
                tasks.append(shutdown_task)

                try:
                    done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    for task in done:
                        if task in (sleep_task, shutdown_task):
                            continue
                        exc = task.exception()
                        if exc:
                            raise exc
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    self.session = None
                    self.audio_in_queue = None
                    self.out_queue = None
                    self._turn_done_event = None
                    self._sleep_event = None
                    self._sleep_after_turn = False
                    self._conversation_active = False
                    self.set_speaking(False)
        finally:
            self._conversation_starting = False
            self._startup_audio_buffer = []

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._wake_audio_queue = asyncio.Queue(maxsize=50)
        self._wake_event = asyncio.Event()
        self._shutdown_event = asyncio.Event()

        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        mic_task = asyncio.create_task(self._listen_audio())
        wake_task = asyncio.create_task(self._wait_for_wakeword())
        music_task = asyncio.create_task(self._watch_music_sleep())

        self.ui.set_state("SLEEPING")
        self.ui.write_log("SYS: JARVIS sleeping. Waiting for wake word.")

        try:
            while True:
                wake_wait = asyncio.create_task(self._wake_event.wait())
                shutdown_wait = asyncio.create_task(self._shutdown_event.wait())
                done, pending = await asyncio.wait(
                    (wake_wait, shutdown_wait),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                if shutdown_wait in done:
                    break

                self._wake_event.clear()
                if self._wake_after_music:
                    self._wake_after_music = False

                try:
                    await self._run_conversation(client)
                except Exception as e:
                    print(f"[JARVIS] ⚠️ {e}")
                    traceback.print_exc()

                self.set_speaking(False)
                await self._reset_wakeword_listening()
                if self._wake_after_music:
                    self._wake_after_music = False
                    if self._wake_event and not self._wake_event.is_set():
                        self._wake_event.set()
                    continue
                self.ui.set_state("SLEEPING")
                self.ui.write_log("SYS: JARVIS sleeping. Waiting for wake word.")
        finally:
            mic_task.cancel()
            wake_task.cancel()
            music_task.cancel()
            await asyncio.gather(mic_task, wake_task, music_task, return_exceptions=True)
            self._shutdown_event = None

def main():
    ui = JarvisUI("face.png")
    jarvis_ref = {"instance": None}
    shutdown_requested = False

    def shutdown(signum=None, frame=None):
        nonlocal shutdown_requested
        if shutdown_requested:
            return
        shutdown_requested = True
        print("\n[JARVIS] Shutting down...")
        jarvis = jarvis_ref.get("instance")
        if jarvis:
            jarvis.request_shutdown()
        ui.root.quit()

    def runner():
        ui.wait_for_api_key()
        jarvis = JarvisLive(ui)
        jarvis_ref["instance"] = jarvis
        asyncio.run(jarvis.run())

    signal.signal(signal.SIGINT, shutdown)

    worker = threading.Thread(target=runner, daemon=True)
    worker.start()
    try:
        ui.root.mainloop()
    except KeyboardInterrupt:
        shutdown()
    finally:
        shutdown()
        worker.join(timeout=2)

if __name__ == "__main__":
    main()
