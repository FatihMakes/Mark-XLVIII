# 🤖 JARVIS Chat Assistant - Quick Start Guide

## Getting Started in 3 Steps

### Step 1: Start JARVIS
```bash
python main.py
```

This will start the JARVIS system with the dashboard on `http://localhost:8000`

### Step 2: Open the Chat Interface
Open your browser and go to:
```
http://localhost:8000/chat
```

### Step 3: Start Chatting
Type your message and press **Enter** to send!

---

## 💬 Command Examples

### Get Information
```
"What time is it?"
"What's the weather today?"
"Show me the news"
```

### Control Your Computer
```
"Open Spotify"
"Take a screenshot"
"Launch Chrome"
```

### Conversational
```
"How are you?"
"Tell me a joke"
"Help me with coding"
```

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Enter** | Send message |
| **Shift + Enter** | New line in message |
| **Click 🗑️** | Clear chat history |
| **Click ⚙️** | Settings (coming soon) |

---

## 🔍 Troubleshooting Quick Fixes

**"Connection failed"**
- Wait 3 seconds (auto-reconnect)
- Refresh page (Ctrl+R or Cmd+R)
- Restart JARVIS

**"No response from JARVIS"**
- Check if Ollama is running (if using local LLM)
- Check if Gemini API key is set in `config/api_keys.json`
- Check browser console for errors (F12)

**"Chat interface not loading"**
- Make sure dashboard is running
- Check port 8000 is not blocked
- Try `http://127.0.0.1:8000/chat`

---

## 🎨 UI Overview

```
┌─────────────────────────────────────┐
│ ◆ JARVIS  🟢 ONLINE   ⚙️  🗑️        │  ← Header
├─────────────────────────────────────┤
│                                     │
│  Hi there! How can I help?          │  ← JARVIS messages (left)
│                                     │
│                    I need a joke!   │  ← Your messages (right)
│                                     │
│        Sure! Why did the...         │
│                                     │
├─────────────────────────────────────┤
│ Type your message here...      [➤]  │  ← Input area
└─────────────────────────────────────┘
```

---

## 🌐 Remote Access

To access JARVIS chat from another device on your network:

1. Find your computer's IP address:
   - **Windows**: `ipconfig` (look for IPv4 Address)
   - **Mac/Linux**: `ifconfig` (look for inet)

2. On another device, visit:
   ```
   http://<YOUR_IP>:8000/chat
   ```

   Example: `http://192.168.1.100:8000/chat`

---

## 📱 Mobile Friendly

The chat interface works great on mobile! Just:
1. Open the same URL on your phone
2. Tap the message field
3. Start typing and send

The interface automatically adapts to smaller screens.

---

## 💡 Tips & Tricks

- **Auto-resize**: Type longer messages and the input box grows automatically
- **Typing indicator**: You'll see "●●●" when JARVIS is processing
- **Timestamps**: Hover over messages to see exact times
- **Timestamps**: Each message shows when it was sent
- **Scroll**: Automatically scrolls to latest message
- **History**: Clear chat with the trash icon when you want to start fresh

---

## 🔧 Configuration

### Change Theme Colors
Edit `dashboard/static/chat.html` and modify the CSS variables:
```css
--accent: #00d9ff;        /* Change this to customize accent color */
--bg-primary: #0a0e1a;    /* Dark background */
```

### Increase History Limit
Edit `dashboard/chat_api.py`:
```python
self.max_history = 100  # Increase to store more messages
```

---

## 📊 System Status

- **Status Badge**: Shows "ONLINE" when connected
- **Green Dot**: Indicates active connection
- **Pulse Animation**: Visual indicator that system is running

---

## 🎯 Next Steps

1. ✅ Start JARVIS (`python main.py`)
2. ✅ Open chat (`http://localhost:8000/chat`)
3. ✅ Send your first message
4. ✅ Explore JARVIS capabilities
5. ✅ Check the full documentation: `dashboard/CHAT_README.md`

---

## 🚀 Advanced Features

### WebSocket Connection
The chat uses WebSocket for real-time, bi-directional communication. This means:
- Instant message delivery
- Real-time streaming responses
- Automatic reconnection on disconnect

### Message History
- Automatically saved in memory
- Persists for your session
- Clear with the trash button

### Integration with JARVIS
Messages are processed through the full JARVIS system, so you get:
- Access to all JARVIS capabilities
- Real-time system monitoring
- Command execution
- Context awareness

---

## ✨ Enjoy!

You're all set! Start exploring what JARVIS can do. Have fun! 🎉

For more details, check out:
- `dashboard/CHAT_README.md` - Full documentation
- `readme.md` - JARVIS system overview
- `config/api_keys.json` - Configuration settings
