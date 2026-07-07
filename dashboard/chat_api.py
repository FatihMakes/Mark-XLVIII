"""
Jarvis Chat API — WebSocket + REST endpoints for real-time chat interface.

Provides:
  - WebSocket endpoint for real-time streaming responses
  - REST endpoint for standard request/response
  - Message history persistence
  - Context window management
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
    _API_AVAILABLE = True
except ImportError:
    _API_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent.parent
MEMORY_DIR = BASE_DIR / "memory" / "chat_history"


class ChatManager:
    """Manage WebSocket connections and chat sessions."""
    
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.chat_history: list[dict] = []
        self.max_history = 100
        
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        
    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass
                
    def add_to_history(self, role: str, content: str, metadata: dict = None):
        """Add message to chat history."""
        msg = {
            "id": len(self.chat_history),
            "timestamp": datetime.now().isoformat(),
            "role": role,
            "content": content,
            "metadata": metadata or {}
        }
        self.chat_history.append(msg)
        
        # Keep history bounded
        if len(self.chat_history) > self.max_history:
            self.chat_history.pop(0)
            
        return msg
        
    def get_history(self, limit: int = 50) -> list[dict]:
        """Get recent chat history."""
        return self.chat_history[-limit:]
        
    async def save_history(self, session_id: str = "default"):
        """Persist chat history to disk."""
        try:
            MEMORY_DIR.mkdir(parents=True, exist_ok=True)
            history_file = MEMORY_DIR / f"{session_id}_{datetime.now().strftime('%Y%m%d')}.json"
            
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self.chat_history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Failed to save chat history: {e}")


# Global chat manager
chat_manager = ChatManager()


def create_chat_router(llm_client) -> "APIRouter":
    """Create FastAPI router with chat endpoints."""
    
    if not _API_AVAILABLE:
        return None
        
    from fastapi import APIRouter
    router = APIRouter(prefix="/api/chat", tags=["chat"])
    
    # ──────────────────────────────────────────────────────────────────
    # REST Endpoints
    # ──────────────────────────────────────────────────────────────────
    
    @router.get("/history")
    async def get_chat_history(limit: int = 50):
        """Get recent chat history."""
        return {"history": chat_manager.get_history(limit)}
    
    
    @router.post("/send")
    async def send_message(request: dict):
        """Send a message and get a response."""
        user_message = request.get("message", "").strip()
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        # Add user message to history
        user_msg = chat_manager.add_to_history("user", user_message)
        
        try:
            # Get response from LLM
            response_text = ""
            if hasattr(llm_client, 'chat_streaming'):
                # Stream the response
                for chunk in llm_client.chat_streaming(user_message):
                    response_text += chunk
            else:
                # Standard response
                response_text = llm_client.chat(user_message)
            
            # Add assistant message to history
            assistant_msg = chat_manager.add_to_history("assistant", response_text)
            
            # Broadcast to all connected clients
            await chat_manager.broadcast({
                "type": "message",
                "data": assistant_msg
            })
            
            return {
                "success": True,
                "user_message": user_msg,
                "assistant_message": assistant_msg
            }
            
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            chat_manager.add_to_history("system", error_msg)
            raise HTTPException(status_code=500, detail=error_msg)
    
    
    @router.post("/clear")
    async def clear_history():
        """Clear chat history."""
        chat_manager.chat_history.clear()
        await chat_manager.broadcast({"type": "history_cleared"})
        return {"success": True, "message": "Chat history cleared"}
    
    
    # ──────────────────────────────────────────────────────────────────
    # WebSocket Endpoint
    # ──────────────────────────────────────────────────────────────────
    
    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for real-time chat."""
        await chat_manager.connect(websocket)
        
        try:
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                msg_type = message_data.get("type", "message")
                
                if msg_type == "message":
                    user_message = message_data.get("content", "").strip()
                    
                    if not user_message:
                        continue
                    
                    # Add user message to history
                    user_msg = chat_manager.add_to_history("user", user_message)
                    
                    # Broadcast user message to all clients
                    await chat_manager.broadcast({
                        "type": "user_message",
                        "data": user_msg
                    })
                    
                    try:
                        # Stream response from LLM
                        response_text = ""
                        
                        if hasattr(llm_client, 'chat_streaming'):
                            for chunk in llm_client.chat_streaming(user_message):
                                response_text += chunk
                                # Stream chunks in real-time
                                await chat_manager.broadcast({
                                    "type": "assistant_chunk",
                                    "content": chunk
                                })
                        else:
                            response_text = llm_client.chat(user_message)
                            await chat_manager.broadcast({
                                "type": "assistant_message",
                                "content": response_text
                            })
                        
                        # Add complete message to history
                        assistant_msg = chat_manager.add_to_history("assistant", response_text)
                        
                        # Notify completion
                        await chat_manager.broadcast({
                            "type": "message_complete",
                            "data": assistant_msg
                        })
                        
                    except Exception as e:
                        error_msg = f"Error processing message: {str(e)}"
                        await chat_manager.broadcast({
                            "type": "error",
                            "message": error_msg
                        })
                        
                elif msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            chat_manager.disconnect(websocket)
        except Exception as e:
            print(f"WebSocket error: {e}")
            chat_manager.disconnect(websocket)
    
    return router
