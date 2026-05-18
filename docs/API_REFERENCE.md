# MARK XXXIX - API Reference

## Available Actions/Tools

### System Control

#### `open_app`
Launch applications on the system.

**Parameters:**
```json
{
  "app_name": "string (required) - Name of application to open"
}
```

**Example:**
```
open_app: {"app_name": "notepad"}
```

**Response:**
```json
{
  "success": true,
  "result": "Application launched successfully"
}
```

---

#### `computer_control`
Control mouse and keyboard.

**Parameters:**
```json
{
  "action": "string - 'click', 'scroll', 'type', 'hotkey'",
  "coordinates": "[x, y] - For click/scroll",
  "text": "string - Text to type",
  "keys": "string - Keys for hotkey (e.g., 'ctrl+s')"
}
```

**Examples:**
```
computer_control: {"action": "click", "coordinates": [500, 300]}
computer_control: {"action": "type", "text": "Hello World"}
computer_control: {"action": "hotkey", "keys": "ctrl+s"}
```

---

#### `desktop`
Desktop and window management.

**Parameters:**
```json
{
  "action": "string - 'screenshot', 'get_windows', 'switch_window', 'minimize', 'maximize'",
  "window_name": "string - Window title (optional)"
}
```

**Examples:**
```
desktop: {"action": "screenshot"}
desktop: {"action": "get_windows"}
desktop: {"action": "switch_window", "window_name": "Microsoft Edge"}
```

---

#### `computer_settings`
Modify system settings.

**Parameters:**
```json
{
  "action": "string - 'brightness', 'volume', 'sleep', 'restart'",
  "value": "number - New value (0-100 for brightness/volume)"
}
```

**Examples:**
```
computer_settings: {"action": "brightness", "value": 75}
computer_settings: {"action": "volume", "value": 50}
```

---

### File Operations

#### `file_controller`
Create, read, modify, and delete files.

**Parameters:**
```json
{
  "action": "string - 'create', 'read', 'write', 'append', 'delete', 'list'",
  "path": "string - File or directory path",
  "content": "string - Content to write/append",
  "recursive": "boolean - For directory operations"
}
```

**Examples:**
```
file_controller: {"action": "create", "path": "/path/to/file.txt", "content": "Hello"}
file_controller: {"action": "read", "path": "/path/to/file.txt"}
file_controller: {"action": "delete", "path": "/path/to/file.txt"}
file_controller: {"action": "list", "path": "/path/to/directory"}
```

**Response:**
```json
{
  "success": true,
  "result": "File content or operation result"
}
```

---

#### `file_processor`
Process documents (PDF, images, text).

**Parameters:**
```json
{
  "file_path": "string - Path to file",
  "action": "string - 'analyze', 'extract_text', 'summarize'",
  "language": "string - Language code (optional)"
}
```

**Examples:**
```
file_processor: {"file_path": "document.pdf", "action": "extract_text"}
file_processor: {"file_path": "image.png", "action": "analyze"}
```

---

### Internet & Web

#### `web_search`
Search information online via DuckDuckGo.

**Parameters:**
```json
{
  "query": "string (required) - Search query",
  "max_results": "number - Max results (default: 5)"
}
```

**Example:**
```
web_search: {"query": "Python async programming", "max_results": 3}
```

**Response:**
```json
{
  "success": true,
  "result": "Search results with snippets and links"
}
```

---

#### `browser_control`
Control web browsers (Chrome, Firefox, Edge).

**Parameters:**
```json
{
  "action": "string - 'open', 'click', 'navigate', 'scroll', 'type', 'wait_for', 'extract_text'",
  "url": "string - URL to open",
  "selector": "string - CSS selector for element",
  "text": "string - Text to type/search for",
  "wait_time": "number - Seconds to wait"
}
```

**Examples:**
```
browser_control: {"action": "open", "url": "https://google.com"}
browser_control: {"action": "type", "selector": "input[type='search']", "text": "AI"}
browser_control: {"action": "click", "selector": "button.submit"}
```

---

#### `youtube_video`
Search and retrieve YouTube content.

**Parameters:**
```json
{
  "query": "string - Video search query",
  "action": "string - 'search', 'get_transcript', 'play'"
}
```

**Examples:**
```
youtube_video: {"query": "machine learning tutorial", "action": "search"}
youtube_video: {"query": "video_url", "action": "get_transcript"}
```

---

### Information & Data

#### `weather_report`
Get weather information.

**Parameters:**
```json
{
  "location": "string (required) - City name or coordinates",
  "units": "string - 'celsius' or 'fahrenheit' (default: 'celsius')"
}
```

**Example:**
```
weather_report: {"location": "New York", "units": "fahrenheit"}
```

**Response:**
```json
{
  "success": true,
  "result": "Temperature, conditions, forecast..."
}
```

---

#### `flight_finder`
Search flight information.

**Parameters:**
```json
{
  "from": "string - Departure city/code",
  "to": "string - Destination city/code",
  "date": "string - Travel date (YYYY-MM-DD)",
  "one_way": "boolean - One-way or round-trip"
}
```

**Example:**
```
flight_finder: {"from": "NYC", "to": "LAX", "date": "2024-12-25"}
```

---

### Communication

#### `send_message`
Send messages via email, SMS, or messaging apps.

**Parameters:**
```json
{
  "recipient": "string - Email or phone number",
  "message": "string - Message content",
  "platform": "string - 'email', 'sms', 'slack', 'telegram' (optional)"
}
```

**Example:**
```
send_message: {"recipient": "user@example.com", "message": "Hello!", "platform": "email"}
```

---

### Development

#### `code_helper`
Code analysis and suggestions.

**Parameters:**
```json
{
  "action": "string - 'analyze', 'optimize', 'debug', 'explain'",
  "code": "string - Code to analyze",
  "language": "string - Programming language"
}
```

**Example:**
```
code_helper: {"action": "analyze", "code": "def hello(): print('hi')", "language": "python"}
```

---

#### `dev_agent`
Development-focused tasks.

**Parameters:**
```json
{
  "task": "string - Development task description",
  "language": "string - Programming language",
  "framework": "string - Framework/library (optional)"
}
```

**Example:**
```
dev_agent: {"task": "Create REST API endpoint", "language": "python", "framework": "flask"}
```

---

### Utilities

#### `screen_processor`
Capture and analyze screen content.

**Parameters:**
```json
{
  "action": "string - 'capture', 'analyze', 'ocr'",
  "region": "[x1, y1, x2, y2] - Screen region (optional, full screen if omitted)"
}
```

**Example:**
```
screen_processor: {"action": "capture"}
screen_processor: {"action": "ocr", "region": [0, 0, 1920, 1080]}
```

---

#### `reminder`
Create and manage reminders.

**Parameters:**
```json
{
  "action": "string - 'create', 'list', 'delete'",
  "title": "string - Reminder title",
  "time": "string - Time or duration (e.g., '2pm', 'in 30 minutes')",
  "id": "string - Reminder ID (for deletion)"
}
```

**Examples:**
```
reminder: {"action": "create", "title": "Meeting", "time": "2pm"}
reminder: {"action": "list"}
reminder: {"action": "delete", "id": "reminder_123"}
```

---

#### `game_updater`
Manage game installations and updates.

**Parameters:**
```json
{
  "action": "string - 'list_games', 'update', 'install', 'uninstall'",
  "game_name": "string - Game name"
}
```

**Example:**
```
game_updater: {"action": "list_games"}
game_updater: {"action": "update", "game_name": "Steam games"}
```

---

## Memory API

### Available Operations

#### Load Memory
```python
from memory.memory_manager import load_memory

memory = load_memory()
# Returns dict with identity, preferences, projects, relationships, wishes, notes
```

#### Update Memory
```python
from memory.memory_manager import update_memory

update_memory("preferences", "favorite_language", "Python")
# Categories: identity, preferences, projects, relationships, wishes, notes
```

#### Format for Prompt
```python
from memory.memory_manager import format_memory_for_prompt

formatted = format_memory_for_prompt(memory)
# Returns formatted string for API context
```

### Memory Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| `identity` | User identity | name, age, location, occupation |
| `preferences` | User preferences | favorite tools, languages, timezone |
| `projects` | Active projects | project names and descriptions |
| `relationships` | Contacts & connections | friend names, work colleagues |
| `wishes` | Goals & aspirations | career goals, travel plans |
| `notes` | General notes | reminders, important info |

---

## Gemini API Integration

### Direct API Usage
```python
from google import genai
from google.genai import types

client = genai.Client(api_key="YOUR_API_KEY")

# Text generation
response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents="Your question here"
)

# With tools
response = client.models.generate_content(
    model="models/gemini-2.5-flash",
    contents="...",
    tools=[tool_definitions]
)

# Audio generation
audio_response = client.models.generate_content(
    model="models/gemini-2.5-flash-native-audio-preview-12-2025",
    contents=[
        types.Part.from_bytes(audio_data, mime_type="audio/pcm")
    ]
)
```

### Model Information

**Current Model:** `models/gemini-2.5-flash-native-audio-preview-12-2025`

**Capabilities:**
- Native audio input/output
- Tool calling (function calling)
- Multi-turn conversations
- Image/document analysis
- Low latency responses

**Rate Limits:** See Google AI Studio dashboard

---

## Error Codes & Responses

### Success Response
```json
{
  "success": true,
  "result": "Operation result or data"
}
```

### Error Response
```json
{
  "success": false,
  "error": "Error description"
}
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| API_KEY_INVALID | Wrong/missing API key | Check config/api_keys.json |
| RATE_LIMIT_EXCEEDED | Too many API calls | Wait or check quota |
| ACTION_NOT_FOUND | Unknown tool name | Check tool name matches |
| PARAMETER_MISSING | Required param missing | Provide all required params |
| PARAMETER_INVALID | Wrong param format | Check parameter types |
| EXECUTION_FAILED | Action execution error | Review action implementation |
| TIMEOUT | Operation took too long | Increase timeout or retry |

---

## Rate Limits & Quotas

### Gemini API Quotas (Free Tier)
- **Requests per minute:** 60
- **Tokens per minute:** 4,000,000
- **Concurrent connections:** 10

### Recovery Strategy
```python
import time

def retry_with_backoff(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except RateLimitError:
            wait_time = 2 ** attempt
            print(f"Rate limited. Waiting {wait_time}s...")
            time.sleep(wait_time)
    raise Exception("Max retries exceeded")
```

---

## Examples

### Complete Conversation Flow
```
User: "Open Chrome and search for weather in New York"

→ Tool Call 1: open_app
   {"app_name": "Chrome"}

→ Tool Call 2: browser_control
   {"action": "type", "selector": "search", "text": "weather new york"}
   
→ Tool Call 3: browser_control
   {"action": "wait_for", "selector": "weather-results"}

→ Tool Call 4: screen_processor
   {"action": "analyze"}

→ Response: "Weather in New York is 72°F, partly cloudy..."
```

### Memory Update Flow
```
User: "Remember I'm learning Python"

→ Action: update_memory
   ("preferences", "learning_language", "Python")

→ Memory persisted to long_term.json

→ Future conversations include this context
```

### Error Recovery Flow
```
Tool Call: browser_control fails
   → Error: "Element not found"

→ Error Handler analyzes failure

→ Recovery: retry with different selector
   OR suggest alternative approach

→ Retry tool call
```

---

## Best Practices

1. **Always validate parameters** before calling tools
2. **Use specific selectors** for web automation
3. **Keep memory entries concise** (< 380 chars each)
4. **Chain related operations** for efficiency
5. **Provide clear context** to Gemini for better planning
6. **Handle failures gracefully** with retry logic
7. **Cache frequently accessed data** when possible
8. **Monitor API usage** to stay within quotas
