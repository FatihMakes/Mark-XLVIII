# MARK XXXIX - System Architecture

## Overview

MARK XXXIX is a cross-platform personal AI assistant that combines voice processing, screen analysis, system control, and intelligent task planning. The system is designed for autonomous operation with deep learning integration via Google Gemini API.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User Interface (PyQt6)                   │
│  - Real-time voice capture/playback                         │
│  - Screen display & webcam feed                             │
│  - Text input & conversation history                        │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                   Main Event Loop                           │
│  - Audio stream management                                  │
│  - Gemini API integration (native audio)                    │
│  - Tool invocation router                                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
    ┌────────────┐ ┌────────────┐ ┌──────────────┐
    │   Agent    │ │  Actions   │ │   Memory     │
    │  Module    │ │  Module    │ │   Module     │
    └────────────┘ └────────────┘ └──────────────┘
```

## Core Modules

### 1. **Main Module** (`main.py`)
The heart of the system - orchestrates all components.

**Key Responsibilities:**
- Initialize Gemini API client with native audio support
- Manage real-time audio streaming (input/output)
- Process API responses and tool calls
- Invoke appropriate action modules based on tool requests
- Handle error recovery and retry logic

**Key Variables:**
- `LIVE_MODEL`: Gemini 2.5 Flash (native audio preview)
- `SEND_SAMPLE_RATE`: 16000 Hz (voice input)
- `RECEIVE_SAMPLE_RATE`: 24000 Hz (voice output)
- `CHUNK_SIZE`: 1024 bytes (streaming buffer)

### 2. **UI Module** (`ui.py`)
PyQt6-based graphical interface.

**Features:**
- Real-time microphone/speaker control
- Screen capture display
- Conversation history
- Resizable & customizable layout
- Transparency controls

### 3. **Agent Module** (`agent/`)
Decision-making and task execution engine.

#### **Planner** (`planner.py`)
- Breaks down high-level goals into executable steps
- Validates tool availability
- Generates tool call sequences
- Max 5 steps per plan
- Rules:
  - Never generates arbitrary Python code
  - Uses available tools only
  - Tools are independent (no chaining results)

#### **Executor** (`executor.py`)
- Executes tool calls sequentially
- Manages subprocess execution
- Handles code generation when needed
- Processes execution results
- Recovers from failures

#### **Error Handler** (`error_handler.py`)
- Analyzes execution failures
- Generates corrective actions
- Provides retry strategies
- Decision logic for recovery

#### **Task Queue** (`task_queue.py`)
- Manages asynchronous task scheduling
- Handles long-running operations
- Provides task status tracking

### 4. **Actions Module** (`actions/`)
16+ specialized action handlers for specific capabilities.

| Action | Purpose |
|--------|---------|
| `open_app.py` | Launch applications by name |
| `file_controller.py` | Create, read, modify, delete files |
| `file_processor.py` | Parse PDFs, images, documents |
| `screen_processor.py` | Capture & analyze screen content |
| `browser_control.py` | Navigate, interact with web browsers |
| `computer_control.py` | Mouse/keyboard simulation |
| `computer_settings.py` | Modify system settings |
| `web_search.py` | Search information via DuckDuckGo |
| `code_helper.py` | Code analysis & suggestions |
| `dev_agent.py` | Development-focused tasks |
| `weather_report.py` | Fetch weather information |
| `youtube_video.py` | Search & retrieve YouTube content |
| `flight_finder.py` | Search flight information |
| `send_message.py` | Send messages via various platforms |
| `desktop.py` | Desktop/window management |
| `reminder.py` | Create & manage reminders |
| `game_updater.py` | Manage game installations |

**Action Interface Pattern:**
```python
def action_name(parameters: dict) -> dict:
    """
    Returns:
        {
            "success": bool,
            "result": str,
            "error": str (if failed)
        }
    """
```

### 5. **Memory Module** (`memory/`)
Persistent long-term memory system.

#### **Memory Manager** (`memory_manager.py`)
- Stores & retrieves long-term memories
- Organized into categories:
  - `identity`: User information
  - `preferences`: User preferences
  - `projects`: Active projects
  - `relationships`: People & connections
  - `wishes`: User goals/desires
  - `notes`: General notes
- Max size constraints:
  - Per value: 380 chars
  - Total memory: 2200 chars
- Thread-safe operations (Lock-based)

#### **Config Manager** (`config_manager.py`)
- Manages configuration settings
- Persistent storage

#### **Long-term Memory** (`long_term.json`)
- JSON-based storage
- Located at: `memory/long_term.json`

### 6. **Config Module** (`config/`)
Configuration and API key management.

**Files:**
- `api_keys.json`: Stores Gemini API key
- `__init__.py`: Configuration exports

## Data Flow

### Voice Interaction Flow

```
1. User speaks
    ↓
2. Microphone captures audio → Audio stream
    ↓
3. Audio chunks sent to Gemini API (native audio)
    ↓
4. Gemini processes with system prompt
    ↓
5. API returns response + tool calls
    ↓
6. Main loop processes tool calls
    ↓
7. Tools execute → Results returned
    ↓
8. Gemini generates follow-up response
    ↓
9. Audio response streamed to speaker
    ↓
10. User hears response
```

### Tool Calling Flow

```
User Request
    ↓
Gemini API Analysis
    ↓
Tool Call Generated (if needed)
    ↓
Route to Action Module
    ↓
Action Execution
    ↓
Result Processing
    ↓
Contextual Response Generation
```

## System Components Integration

### Gemini API Integration
- **Model**: `models/gemini-2.5-flash-native-audio-preview-12-2025`
- **Features**:
  - Native audio streaming (low latency)
  - Tool calling (function calling)
  - Multi-turn conversations
  - Screen image analysis
- **Flow**: Voice → API → Response + Tools → Execution

### Tool System
- **Registration**: Tools defined in planner prompt
- **Invocation**: Gemini calls via `tool_use` responses
- **Execution**: Router in `main.py` dispatches to action modules
- **Context**: Tool results passed back to Gemini for context

### Memory System
- **Integration Point**: Loaded at startup, formatted into system prompt
- **Updates**: Executed after successful tasks
- **Persistence**: JSON file maintained throughout runtime

### Error Handling
- **Detection**: Try-catch in executor
- **Analysis**: Error handler analyzes failure
- **Recovery**: Generates corrective action
- **Retry**: Attempts recovery before failure

## Cross-Platform Support

### Platform-Specific Handling
- **Windows**: 
  - `comtypes`, `pycaw` for audio control
  - `pywinauto` for window management
  - `win10toast` for notifications
- **macOS**: 
  - Native accessibility APIs
  - AppleScript support
- **Linux**:
  - X11/Wayland compatible
  - Native command execution

### Abstraction Layer
- Platform detection via `sys.platform`
- Conditional imports (see `pyproject.toml`)
- Normalized APIs across OS

## File Organization

```
MyJarvis/
├── main.py              # Entry point & event loop
├── ui.py                # PyQt6 interface
├── requirements.txt     # Dependencies
├── pyproject.toml       # Project metadata
├── setup.py             # Installation script
│
├── actions/             # 16+ action modules
│   ├── open_app.py
│   ├── file_controller.py
│   └── ... (14 more)
│
├── agent/               # AI decision engine
│   ├── planner.py       # Task planning
│   ├── executor.py      # Task execution
│   ├── error_handler.py # Error recovery
│   └── task_queue.py    # Async scheduling
│
├── memory/              # Persistent memory
│   ├── memory_manager.py
│   ├── config_manager.py
│   ├── long_term.json   # Memory storage
│   └── __init__.py
│
├── config/              # Configuration
│   ├── api_keys.json    # API credentials
│   └── __init__.py
│
└── core/                # Core resources
    └── prompt.txt       # System prompt
```

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| UI Framework | PyQt6 |
| AI Model | Google Gemini 2.5 Flash |
| API Client | google-genai |
| Audio Processing | sounddevice, pyaudio |
| Web Automation | Playwright, Selenium (via actions) |
| Computer Control | pyautogui, pyperclip |
| Screen Capture | mss, opencv-python |
| Document Processing | beautifulsoup4, python-pptx |
| Search | duckduckgo-search |
| Notifications | win10toast (Windows), native (macOS/Linux) |

## Performance Considerations

1. **Audio Streaming**: Chunks of 1024 bytes at 16000 Hz for low latency
2. **Memory**: Long-term memory limited to 2200 chars for efficient API context
3. **Tool Calling**: Max 5 steps per plan to avoid excessive API calls
4. **Threading**: Audio I/O uses separate threads to prevent blocking
5. **Caching**: Screen captures cached between analyses

## Security Considerations

1. **API Keys**: Stored in `config/api_keys.json` (not committed to git)
2. **Sensitive Actions**: File/system operations require explicit user confirmation
3. **Subprocess Execution**: Limited to necessary tools only
4. **Memory**: Long-term memory stored locally, not synced

## Extension Points

### Adding New Actions
1. Create module in `actions/`
2. Implement action function with standard interface
3. Add tool definition to planner prompt
4. Import and register in `main.py`

### Adding New Agent Capabilities
1. Extend `agent/executor.py` with new execution type
2. Add tool definitions to planner
3. Implement error handlers in `error_handler.py`

### Customizing Memory Categories
1. Modify `memory/_empty_memory()` function
2. Update memory manager retrieval logic
3. Update formatting in `format_memory_for_prompt()`

## Limitations & Trade-offs

1. **Tool Execution**: Limited to defined actions only
2. **Memory Size**: Constraint for API context window optimization
3. **Audio Latency**: Dependent on network & Gemini API response time
4. **Screen Analysis**: Captures & processes at moment of request
5. **Async Operations**: Task queue requires explicit scheduling

## Future Enhancements

1. Multi-agent coordination
2. Advanced memory indexing & retrieval
3. Offline fallback modes
4. Extended tool ecosystem
5. Performance profiling & optimization
