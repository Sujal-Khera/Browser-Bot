"""
browserbot/server/ws_manager.py — WebSocket connection manager for session-specific diagnostic streaming.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from fastapi import WebSocket

log = logging.getLogger(__name__)


class SessionWSManager:
    """Manages active session-specific WebSocket connections and event broadcasting."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        """Accepts a connection and registers it under the specific session ID."""
        await websocket.accept()
        async with self._lock:
            if session_id not in self._connections:
                self._connections[session_id] = set()
            self._connections[session_id].add(websocket)
        log.info("WebSocket client connected to session", extra={"session_id": session_id})

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Removes a connection from a session's registry."""
        async with self._lock:
            if session_id in self._connections:
                self._connections[session_id].discard(websocket)
                if not self._connections[session_id]:
                    del self._connections[session_id]
        log.info("WebSocket client disconnected from session", extra={"session_id": session_id})

    async def broadcast(self, session_id: str, event_data: dict[str, Any]) -> None:
        """Broadcasts event data to all connected clients for a given session ID in parallel."""
        async with self._lock:
            sockets = list(self._connections.get(session_id, []))

        if not sockets:
            return

        log.debug(
            "Broadcasting stage event to session clients",
            extra={"session_id": session_id, "stage": event_data.get("stage"), "client_count": len(sockets)}
        )

        for ws in sockets:
            try:
                await ws.send_json(event_data)
            except Exception as exc:
                log.warning(
                    "Failed to send message over WebSocket, cleaning up client",
                    extra={"session_id": session_id, "error": str(exc)}
                )
                await self.disconnect(session_id, ws)

    async def cleanup_session(self, session_id: str) -> None:
        """Closes and cleans up all active WebSocket connections for a completed session."""
        async with self._lock:
            sockets = list(self._connections.pop(session_id, []))

        if not sockets:
            return

        log.info("Cleaning up WebSocket session", extra={"session_id": session_id, "closed_connections": len(sockets)})
        for ws in sockets:
            try:
                await ws.close()
            except Exception:
                pass


# Global singleton instance
ws_manager = SessionWSManager()
