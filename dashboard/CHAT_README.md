# 🤖 JARVIS Chat Assistant

## Overview

The **JARVIS Chat Assistant** is a modern, real-time web-based chat interface that connects to your MARK XLVII AI system. It provides a clean, intuitive UI for interacting with JARVIS through your browser with WebSocket-powered real-time messaging.

## ✨ Features

- 🎯 **Real-time WebSocket Communication** - Instant message delivery with streaming responses
- 💬 **Beautiful Modern UI** - Cyberpunk-inspired dark theme with smooth animations
- 📱 **Responsive Design** - Works seamlessly on desktop and mobile devices
- 💾 **Message History** - Automatically saves and displays conversation history
- ⌨️ **Rich Input** - Multi-line text input with Enter-to-send (Shift+Enter for new lines)
- 🔄 **Auto-reconnect** - Automatically reconnects if the connection drops
- ✅ **Typing Indicators** - See when JARVIS is processing your message
- 🎨 **Smooth Animations** - Professional pop-in effects and transitions

## 🚀 Quick Start

### 1. Access the Chat Interface

Open your browser and navigate to:
```
http://localhost:8000/chat
```

If accessing from another machine on your network:
```
http://<YOUR_IP>:8000/chat
```

### 2. Start Chatting

1. Type your message in the input field at the bottom
2. Press **Enter** to send (or click the send button ➤)
3. Use **Shift+Enter** to create multi-line messages
4. JARVIS will respond in real-time

## 🔧 Configuration

### Backend Integration

The chat interface is automatically integrated with your JARVIS system through:

- **WebSocket Endpoint**: `/api/chat/ws` - Real-time bi-directional communication
- **History Endpoint**: `/api/chat/history` - Retrieve past messages
- **Dashboard Integration**: Messages are forwarded to the main JARVIS dashboard

### Environment Setup

Make sure these dependencies are installed:

```bash
pip install fastapi "uvicorn[standard]" cryptography
```

They should already be in your `requirements.txt`, but if you encounter issues:

```bash
pip install -r requirements.txt
```

## 📝 Usage Examples

### Simple Questions
```
User: What time is it?
JARVIS: It is currently 3:45 PM
```

### System Commands
```
User: Open Spotify
JARVIS: Opening Spotify...
```

### Information Requests
```
User: What's the weather like?
JARVIS: The weather in your location is...
```

### Multi-turn Conversations
```
User: Tell me about the weather
JARVIS: [Provides weather info]
User: Will I need an umbrella?
JARVIS: Based on the forecast...
```

## 🎨 UI Components

### Header
- **JARVIS Logo** with pulsing indicator
- **Online Status** badge
- **Settings** button (⚙️)
- **Clear Chat** button (🗑️)

### Chat Area
- Messages appear with smooth slide-in animations
- User messages align to the right (blue tint)
- JARVIS messages align to the left (cyan tint)
- Timestamps shown for each message
- Typing indicator shows when JARVIS is processing

### Input Area
- Multi-line textarea with auto-resize
- Send button with hover effects
- Placeholder text with helpful hints

## 🔌 API Endpoints

### WebSocket: `/api/chat/ws`

**Send:**
```json
{
  "type": "message",
  "content": "Your message here",
  "timestamp": "2026-07-07T10:37:19.433+02:00"
}
```

**Receive:**
```json
{
  "type": "user_message",
  "data": {
    "id": 1,
    "timestamp": "2026-07-07T10:37:19.433+02:00",
    "role": "user",
    "content": "Your message"
  }
}
```

### REST: `GET /api/chat/history`

**Response:**
```json
{
  "history": [
    {
      "id": 0,
      "timestamp": "2026-07-07T10:37:19.433+02:00",
      "role": "user",
      "content": "Message text"
    }
  ]
}
```

## 🐛 Troubleshooting

### Chat interface not loading
- **Check**: Is the dashboard server running? `http://localhost:8000`
- **Solution**: Start JARVIS with `python main.py`

### Messages not sending
- **Check**: Browser console for errors (F12 → Console)
- **Check**: Is the WebSocket connection active? (look for "✓ Connected to JARVIS")
- **Solution**: Refresh the page or restart the server

### Connection drops frequently
- **Check**: Is your network stable?
- **Solution**: The interface will auto-reconnect; it should recover within 3 seconds
- **Advanced**: Check firewall rules that might block WebSocket connections

### JARVIS not responding
- **Check**: Is the LLM server (Ollama/LM Studio) running?
- **Check**: Is the Gemini API key configured in `config/api_keys.json`?
- **Solution**: Start Ollama or your LLM provider

## 🛠️ Advanced Configuration

### Change Port
Edit `dashboard/server.py`:
```python
PORT = 8000  # Change this to your desired port
```

### Custom Styling
Edit the `<style>` section in `dashboard/static/chat.html` to customize colors:

```css
:root {
  --accent: #00d9ff;        /* Cyan accent color */
  --bg-primary: #0a0e1a;    /* Dark background */
  --text-primary: #e0e8ff;  /* Light text */
}
```

### Message History Limit
The chat keeps the last 100 messages in memory. To change:

Edit `dashboard/chat_api.py`:
```python
self.max_history = 100  # Change this value
```

## 📊 System Requirements

- **Python**: 3.11 or 3.12
- **Browser**: Chrome, Firefox, Safari, Edge (any modern browser with WebSocket support)
- **Network**: LAN/WiFi connection for remote access
- **Dependencies**: FastAPI, Uvicorn, Cryptography

## 🔒 Security

- **Local Network Only**: The dashboard listens on `0.0.0.0:8000` but requires authentication
- **Session-based Encryption**: AES-256-CBC encryption for sensitive data
- **HTTPS Support**: Optional SSL/TLS certificates for secure connections

## 📚 Integration with JARVIS

The chat interface integrates with JARVIS through:

1. **Command Queue**: Messages are added to `_command_queue` for processing
2. **Response Streaming**: Responses are streamed in real-time via WebSocket
3. **Dashboard Broadcast**: Messages are broadcast to all connected clients
4. **Memory System**: Conversation history is optionally saved to disk

## 🚨 Performance Tips

- Keep chat history limit reasonable (100-500 messages)
- Close unused chat tabs to reduce server load
- For multiple users, ensure server has adequate resources
- Monitor WebSocket connections in production

## 🎯 Future Enhancements

Planned features for upcoming versions:

- [ ] File upload support for document processing
- [ ] Voice input/output integration
- [ ] Message search functionality
- [ ] User preferences and settings persistence
- [ ] Multi-session support
- [ ] Rate limiting and usage statistics
- [ ] Export conversation as PDF/TXT
- [ ] Custom system prompts per session

## 📞 Support

For issues or feature requests:

1. Check this documentation
2. Review browser console for errors
3. Check JARVIS system logs
4. Verify dependencies are installed: `pip install -r requirements.txt`

## 📄 License

Same as MARK XLVII: Creative Commons BY-NC 4.0
Personal and non-commercial use only.

---

**Enjoy your conversations with JARVIS!** 🚀
