# 🏗️ JARVIS Chat Assistant - Architecture Guide

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            USER BROWSER                                    │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐  │
│   │                     chat.html (Chat Interface)                      │  │
│   │                                                                     │  │
│   │  [Header: JARVIS Logo, Status, Settings]                          │  │
│   │  [Message Area: Conversation History]                             │  │
│   │  [Input: Message Field + Send Button]                             │  │
│   │                                                                     │  │
│   │  ┌──────────────────────────────────────────────────────────────┐ │  │
│   │  │ JavaScript WebSocket Client                                 │ │  │
│   │  │ ├─ connect to /api/chat/ws                                  │ │  │
│   │  │ ├─ send messages (JSON)                                     │ │  │
│   │  │ ├─ receive responses (streaming)                            │ │  │
│   │  │ ├─ auto-reconnect on disconnect                            │ │  │
│   │  │ └─ ping/pong keep-alive                                    │ │  │
│   │  └──────────────────────────────────────────────────────────────┘ │  │
│   └─────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│                         HTTP & WebSocket                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕
                          localhost:8000
                                    ↕
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI SERVER (server.py)                         │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ HTTP Routes                                                        │   │
│  ├─ GET /                 → login page                               │   │
│  ├─ GET /chat             → chat.html interface                      │   │
│  ├─ GET /login            → login page                               │   │
│  ├─ POST /login           → authenticate user                        │   │
│  └─ GET /api/chat/history → message history                          │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ WebSocket Routes                                                   │   │
│  ├─ WebSocket /ws                   → Main JARVIS dashboard          │   │
│  ├─ WebSocket /api/chat/ws          → Chat interface (NEW!)          │   │
│  └─ WebSocket /ws/phone-audio       → Phone microphone              │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ Chat API (chat_api.py integration)                                 │   │
│  │                                                                    │   │
│  │  ChatManager                                                       │   │
│  │  ├─ Manage WebSocket connections                                 │   │
│  │  ├─ Track message history                                        │   │
│  │  ├─ Broadcast to all clients                                     │   │
│  │  └─ Persist history to disk                                      │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ Authentication & Security                                          │   │
│  │ ├─ Session tokens                                                 │   │
│  │ ├─ AES-256-CBC encryption                                         │   │
│  │ ├─ Bearer token validation                                        │   │
│  │ └─ CORS protection                                                │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕
                                Command Queue
                                    ↕
┌─────────────────────────────────────────────────────────────────────────────┐
│                      JARVIS MAIN SYSTEM (main.py)                          │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ Command Processing                                                 │   │
│  │ ├─ Receive from chat interface                                    │   │
│  │ ├─ Process through JARVIS system                                  │   │
│  │ ├─ Execute actions (open app, web search, etc)                   │   │
│  │ ├─ Generate response with LLM                                     │   │
│  │ └─ Send response back to all clients                             │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ JARVIS Components                                                  │   │
│  │ ├─ UI (PyQt6 interface)                                           │   │
│  │ ├─ Memory System                                                   │   │
│  │ ├─ Action Handlers                                                │   │
│  │ ├─ STT (Speech-to-Text)                                           │   │
│  │ ├─ TTS (Text-to-Speech)                                           │   │
│  │ ├─ System Monitor                                                 │   │
│  │ └─ Browser Control                                                │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────┐   │
│  │ LLM Client (llm_client.py)                                         │   │
│  │ ├─ Ollama (local, default)                                        │   │
│  │ ├─ OpenAI-compatible (LM Studio, LocalAI, Jan)                   │   │
│  │ ├─ Streaming response support                                     │   │
│  │ └─ Message history context                                        │   │
│  └────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↕
┌─────────────────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES (Optional)                             │
│                                                                             │
│  • Ollama (Port 11434) - Local LLM engine                                  │
│  • LM Studio (Port 1234) - Alternative local LLM                          │
│  • Gemini API - Google's generative AI                                     │
│  • DuckDuckGo - Web search                                                 │
│  • External APIs - Weather, flights, etc                                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Message Flow

### User Sends Message

```
User Types Message
      ↓
[Enter Key]
      ↓
JavaScript validates input
      ↓
Send via WebSocket /api/chat/ws
      ↓
FastAPI receives message
      ↓
Add to JARVIS command queue
      ↓
Broadcast to dashboard
      ↓
JARVIS processes command
      ↓
LLM generates response
      ↓
Response sent via WebSocket
      ↓
Browser receives streaming response
      ↓
Display in chat UI with animation
      ↓
Store in message history
```

## Data Flow

### Request Path
```
Browser (chat.html)
    ↓
[WebSocket Message]
{
  "type": "message",
  "content": "User message",
  "timestamp": "2026-07-07T10:37:19Z"
}
    ↓
FastAPI server (/api/chat/ws)
    ↓
ChatManager.add_to_history()
    ↓
JARVIS _command_queue.put()
    ↓
JARVIS system processes
    ↓
Generate LLM response
```

### Response Path
```
LLM generates response
    ↓
Response text streamed
    ↓
ChatManager.add_to_history()
    ↓
Broadcast via WebSocket
    ↓
Browser receives chunks
    ↓
Update UI in real-time
    ↓
Show complete message
    ↓
Scroll to bottom
```

## Connection States

```
DISCONNECTED
      ↓
connect()
      ↓
CONNECTING (attempting handshake)
      ↓
CONNECTED ← ← → Keep-alive (ping/pong every 30s)
      ↓
Connection drops
      ↓
RECONNECTING (wait 3s)
      ↓
[Retry]
```

## File Organization

```
dashboard/
├── server.py
│   ├── DashboardServer class
│   ├── _build_app() method
│   ├── Chat routes (NEW)
│   │   ├── GET /chat → serves chat.html
│   │   ├── GET /api/chat/history → message history
│   │   └── WebSocket /api/chat/ws → real-time chat
│   └── serve() method
│
├── chat_api.py (NEW)
│   ├── ChatManager class
│   │   ├── connect(websocket)
│   │   ├── disconnect(websocket)
│   │   ├── broadcast(message)
│   │   ├── add_to_history()
│   │   └── save_history()
│   └── create_chat_router() function
│
├── static/
│   ├── chat.html (NEW) - Chat interface
│   ├── app.html - Existing dashboard
│   ├── login.html - Login page
│   └── crypto-js.min.js - Encryption
│
└── __init__.py
```

## Component Interactions

```
┌─────────────────┐
│   chat.html     │
│  (JavaScript)   │
└────────┬────────┘
         │ WebSocket
         ↓
┌────────────────────────┐
│   FastAPI Routes       │
│  (server.py)           │
└────────┬───────────────┘
         │
         ├─→ /chat (serves HTML)
         ├─→ /api/chat/history (gets messages)
         └─→ /api/chat/ws (WebSocket)
              │
              ↓
         ┌──────────────┐
         │ ChatManager  │
         │ (chat_api.py)│
         └──────┬───────┘
                │
        ┌───────┴────────┐
        ↓                ↓
    ┌────────┐      ┌─────────┐
    │ History│      │ Broadcast│
    └────────┘      └─────────┘
        │                │
        ↓                ↓
    [Disk]         [All Clients]
    [Memory]       [Dashboard]
```

## Scalability Considerations

```
Single Instance
├─ ~100-500 concurrent connections
├─ ~1KB per stored message
├─ WebSocket pool management
└─ Auto-reconnect handling

Multiple Instances (Future)
├─ Load balancer (nginx/HAProxy)
├─ Shared message store (Redis)
├─ Session persistence (database)
└─ Cross-instance broadcasting
```

## Security Layers

```
Network Level
├─ HTTPS/WSS support (optional)
├─ Firewall rules (auto-configured)
└─ Local network only (default)

Application Level
├─ Session tokens
├─ Bearer authentication
├─ AES-256-CBC encryption
└─ Input validation & sanitization

Data Level
├─ HTML escaping
├─ JSON validation
├─ Type checking
└─ Error handling
```

## Performance Optimization

```
Client Side
├─ WebSocket for low-latency
├─ Message batching
├─ Virtual scrolling (future)
└─ CSS transitions (GPU accelerated)

Server Side
├─ Async I/O (asyncio)
├─ Connection pooling
├─ Message queue
├─ Auto-pruning (max 100 messages)
└─ Broadcast optimization
```

---

This architecture enables:
✅ Real-time communication
✅ Scalability
✅ Security
✅ Reliability
✅ Integration with JARVIS system
✅ Future extensibility
