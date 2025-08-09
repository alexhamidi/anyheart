"""WebSocket connection manager for agent sessions"""

import asyncio
from typing import Dict, Optional
from fastapi import WebSocket
from src.logger import get_logger

logger = get_logger(__name__)


class WebSocketManager:
    """Manages WebSocket connections for agent sessions"""

    def __init__(self):
        self.connections: Dict[str, WebSocket] = {}
        self.locks: Dict[str, asyncio.Lock] = {}

    async def connect(self, session_id: str, websocket: WebSocket):
        """Connect a WebSocket for a session"""
        await websocket.accept()
        self.connections[session_id] = websocket
        self.locks[session_id] = asyncio.Lock()
        logger.info(f"WebSocket connected for session: {session_id}")

    async def disconnect(self, session_id: str):
        """Disconnect WebSocket for a session"""
        if session_id in self.connections:
            del self.connections[session_id]
        if session_id in self.locks:
            del self.locks[session_id]
        logger.info(f"WebSocket disconnected for session: {session_id}")

    async def send_message(self, session_id: str, message: dict):
        """Send message to session WebSocket"""
        if session_id not in self.connections:
            logger.warning(f"No WebSocket connection for session: {session_id}")
            return False

        try:
            async with self.locks[session_id]:
                await self.connections[session_id].send_json(message)
            return True
        except Exception as e:
            logger.error(f"Failed to send WebSocket message to {session_id}: {e}")
            await self.disconnect(session_id)
            return False

    async def receive_message(self, session_id: str) -> Optional[dict]:
        """Receive message from session WebSocket"""
        if session_id not in self.connections:
            return None

        try:
            return await self.connections[session_id].receive_json()
        except Exception as e:
            logger.error(f"Failed to receive WebSocket message from {session_id}: {e}")
            await self.disconnect(session_id)
            return None

    def is_connected(self, session_id: str) -> bool:
        """Check if session has active WebSocket connection"""
        return session_id in self.connections


# --- global websocket manager instance ---
ws_manager = WebSocketManager()
