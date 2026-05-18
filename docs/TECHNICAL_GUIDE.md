# MARK XXXIX - Technical Guide

## Table of Contents
1. [Setup & Installation](#setup--installation)
2. [Configuration](#configuration)
3. [Running the Application](#running-the-application)
4. [Development Guide](#development-guide)
5. [Action Module Development](#action-module-development)
6. [API Integration](#api-integration)
7. [Memory System](#memory-system)
8. [Troubleshooting](#troubleshooting)

## Setup & Installation

### Prerequisites
- Python 3.11 or 3.12
- Microphone (for voice input)
- Speaker (for audio output)
- Stable internet connection (for Gemini API)
- 2GB+ free disk space

### Installation Steps

```bash
# Clone the repository
git clone https://github.com/FatihMakes/Mark-XXXIX.git
cd Mark-XXXIX

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for web automation)
playwright install

# Verify installation
python main.py --version
```

### OS-Specific Setup

#### Windows
```bash
# Additional dependencies
pip install comtypes pycaw win10toast pywinauto

# Note: Some windows-specific modules require Visual C++ redistributables
# If issues occur, download from https://support.microsoft.com/en-us/help/2977003
```

#### macOS
```bash
# May require Xcode Command Line Tools
xcode-select --install

# For accessibility features
# Grant Full Disk Access to Terminal in System Preferences → Security
```

#### Linux
```bash
# Install system dependencies
sudo apt-get install python3-dev libpulse-dev libportaudio2

# For X11 support (Wayland compatibility pending)
# Ensure DISPLAY environment variable is set
```

## Configuration

### API Key Setup

1. Get free Gemini API key:
   - Visit: https://aistudio.google.com/apikey
   - Create new project
   - Enable Generative Language API
   - Copy API key

2. Create `config/api_keys.json`:
```json
{
  "gemini_api_key": "your-api-key-here"
}
```

3. Never commit `api_keys.json` to git (included in `.gitignore`)

### System Prompt Configuration

Edit `core/prompt.txt` to customize:
- Assistant personality
- Behavior constraints
- Available tools
- Response style

Example:
```
You are MARK XXXIX, a personal AI assistant.
Your capabilities include: ...
[Tool definitions]
```

### Audio Configuration

Modify in `main.py`:
```python
CHANNELS           = 1         # Mono audio
SEND_SAMPLE_RATE   = 16000     # Input rate (Hz)
RECEIVE_SAMPLE_RATE = 24000    # Output rate (Hz)
CHUNK_SIZE         = 1024      # Buffer size (bytes)
```

### Memory Configuration

Adjust in `memory/memory_manager.py`:
```python
MAX_VALUE_LENGTH = 380    # Max chars per memory value
MEMORY_MAX_CHARS = 2200   # Total memory limit
```

## Running the Application

### Standard Launch
```bash
python main.py
```

### Command-line Options
```bash
# Run with debug logging
python main.py --debug

# Run with specific config file
python main.py --config /path/to/config.json

# Run headless (no UI)
python main.py --headless

# Test audio setup
python main.py --test-audio
```

### First Run Checklist
1. ✅ API key configured in `config/api_keys.json`
2. ✅ Microphone working and unmuted
3. ✅ Speaker functional
4. ✅ Internet connection active
5. ✅ All dependencies installed

## Development Guide

### Project Structure
```
MyJarvis/
├── main.py              # Main event loop
├── ui.py                # PyQt6 UI
├── actions/             # Action modules (16+)
├── agent/               # AI agent modules
├── memory/              # Memory system
├── config/              # Configuration
├── core/                # Core resources
└── docs/                # Documentation
```

### Code Style

Follow PEP 8 with these conventions:
```python
# Imports
import asyncio
from typing import Callable, Dict

# Functions
def function_name(param1: str, param2: int) -> bool:
    """
    Brief description.
    
    Args:
        param1: Description
        param2: Description
    
    Returns:
        Description
    """
    pass

# Type hints
result: Dict[str, any] = {}
callback: Callable | None = None
```

### Adding Logging
```python
import logging

logger = logging.getLogger(__name__)
logger.info("Operation completed")
logger.error("An error occurred", exc_info=True)
```

### Testing Actions
```python
# Test an action module
from actions.open_app import open_app

result = open_app({"app_name": "notepad"})
print(result)  # Should return {"success": True, "result": "..."}
```

## Action Module Development

### Action Module Template
```python
"""
Module: example_action.py
Purpose: Brief description of what this action does
"""

def example_action(params: dict) -> dict:
    """
    Main function called by executor.
    
    Args:
        params: {
            "param1": str,
            "param2": int
        }
    
    Returns:
        {
            "success": bool,
            "result": str,     # Success message
            "error": str       # Error message if failed
        }
    """
    try:
        param1 = params.get("param1", "")
        param2 = params.get("param2", 0)
        
        # Implementation here
        
        return {
            "success": True,
            "result": "Action completed successfully"
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
```

### Registering New Action

1. **Create** `actions/new_action.py`
2. **Import** in `main.py`:
```python
from actions.new_action import new_action
```

3. **Register** tool in planner prompt (`core/prompt.txt`):
```
new_action
  param1: string (required)
  param2: integer (optional, default: 0)
```

4. **Add** to executor's tool dispatcher in `main.py`:
```python
elif tool_name == "new_action":
    result = new_action(tool_input)
```

### Best Practices

1. **Error Handling**: Always wrap in try-except
2. **Validation**: Check parameter types and ranges
3. **Logging**: Log important operations
4. **Documentation**: Clear docstrings
5. **Isolation**: No global state modifications
6. **Testing**: Test independently before integration

## API Integration

### Gemini API Setup

```python
from google import genai
from google.genai import types

# Initialize
client = genai.Client(api_key="YOUR_API_KEY")

# Configure model
model_name = "models/gemini-2.5-flash-native-audio-preview-12-2025"

# For native audio
config = types.GenerationConfig(
    temperature=0.7,
    max_output_tokens=1024
)
```

### Tool Calling Example

```python
tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="open_app",
                description="Open an application",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "app_name": types.Schema(
                            type=types.Type.STRING,
                            description="Name of app to open"
                        )
                    },
                    required=["app_name"]
                )
            )
        ]
    )
]

response = client.models.generate_content(
    model=model_name,
    contents=[...],
    tools=tools
)
```

### Streaming Audio

```python
# Input stream (microphone)
audio_queue = []
with sd.InputStream(
    samplerate=16000,
    channels=1,
    blocksize=1024,
    callback=lambda indata, *args: audio_queue.append(indata.copy())
):
    pass

# Output stream (speaker)
with sd.OutputStream(
    samplerate=24000,
    channels=1
) as stream:
    stream.write(audio_data)
```

### Error Handling

```python
from google.api_core import exceptions

try:
    response = client.models.generate_content(...)
except exceptions.ResourceExhausted:
    logger.error("API quota exceeded")
except exceptions.InvalidArgument as e:
    logger.error(f"Invalid request: {e}")
except exceptions.GoogleAPIError as e:
    logger.error(f"API error: {e}")
```

## Memory System

### Memory Structure

```json
{
  "identity": {
    "name": "User name",
    "location": "Current location"
  },
  "preferences": {
    "favorite_language": "Python",
    "timezone": "EST"
  },
  "projects": {
    "project_name": "Description"
  },
  "relationships": {
    "contact_name": "Relationship"
  },
  "wishes": {
    "goal_title": "Goal description"
  },
  "notes": {
    "note_title": "Note content"
  }
}
```

### Memory Operations

```python
from memory.memory_manager import (
    load_memory,
    update_memory,
    format_memory_for_prompt
)

# Load memory
memory = load_memory()

# Update memory
update_memory("preferences", "timezone", "PST")

# Format for API
formatted = format_memory_for_prompt(memory)
```

### Memory Constraints

- **Per Value**: 380 characters max
- **Total Memory**: 2200 characters max
- **Auto-trim**: Excess values trimmed from end
- **Thread-safe**: Lock-protected operations

### Memory Best Practices

1. **Keep concise**: Use 1-2 sentences per memory
2. **Update selectively**: Only update changed info
3. **Category correctly**: Use appropriate category
4. **Trim old**: Remove outdated memories manually
5. **Backup**: Periodic backup of `long_term.json`

## Troubleshooting

### Common Issues

#### 1. "ModuleNotFoundError" on startup
```bash
# Solution: Install missing module
pip install <module_name>

# For OS-specific dependencies
pip install -r requirements.txt
```

#### 2. Microphone not detected
```python
import sounddevice as sd

# List available devices
print(sd.query_devices())

# Test specific device in code:
# Change device_id in main.py InputStream
```

#### 3. API key authentication fails
```bash
# Verify key format
cat config/api_keys.json

# Regenerate key from https://aistudio.google.com/apikey
# Ensure no trailing newlines/spaces
```

#### 4. Audio stuttering/lag
- Increase `CHUNK_SIZE` (currently 1024)
- Reduce background applications
- Check network latency: `ping api.google.com`

#### 5. Screen capture fails (Linux)
```bash
# Ensure DISPLAY is set
echo $DISPLAY

# If empty, set it:
export DISPLAY=:0
```

#### 6. Tool calls not executing
- Check tool name matches exactly in planner prompt
- Verify tool_input JSON format
- Review executor's tool dispatcher
- Check action module for exceptions

### Debug Mode

Enable detailed logging:

```python
# In main.py
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

### Performance Profiling

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run code section

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats()
```

### Getting Help

1. Check logs in terminal output
2. Review [Architecture](ARCHITECTURE.md)
3. Search existing issues on GitHub
4. Enable debug mode and capture output
5. Check audio/microphone settings on OS level

## Performance Optimization

### Memory Optimization
```python
# Use generators for large datasets
def process_large_file(filepath):
    with open(filepath) as f:
        for line in f:
            yield line.strip()
```

### API Call Optimization
```python
# Cache results when possible
from functools import lru_cache

@lru_cache(maxsize=128)
def get_api_response(query):
    return client.models.generate_content(query)
```

### Audio Performance
```python
# Use appropriate chunk size
# Smaller = lower latency, higher CPU
# Larger = higher latency, lower CPU
CHUNK_SIZE = 2048  # Default 1024
```

## Deployment

### Creating Executable
```bash
# Using PyInstaller
pip install pyinstaller

pyinstaller --onefile --windowed \
  --add-data "core:core" \
  --add-data "config:config" \
  main.py
```

### Docker Deployment
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt
RUN playwright install

CMD ["python", "main.py"]
```

### System Integration
- **Windows**: Add to startup via Task Scheduler
- **macOS**: Use LaunchAgent (plist file)
- **Linux**: SystemD service or cron

## Monitoring & Logging

### Log Locations
- Console output: Real-time logs
- File logging: Configure in main.py
- API logs: Review Gemini console

### Monitoring Metrics
- API response time
- Tool execution time
- Memory usage
- Audio latency
