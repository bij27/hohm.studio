"""
WebSocket Manager for Yoga Session Remote Control

Handles real-time communication between desktop browser and phone remote.
"""

import asyncio
import random
import string
from typing import Dict, Set, Optional
from fastapi import WebSocket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json


@dataclass
class YogaRoom:
    """Represents a yoga session room with connected clients."""
    code: str
    created_at: datetime
    desktop: Optional[WebSocket] = None
    remotes: Set[WebSocket] = field(default_factory=set)
    state: dict = field(default_factory=lambda: {
        "status": "waiting",  # waiting, calibrating, countdown, active, paused, complete
        "currentPose": None,
        "poseIndex": 0,
        "totalPoses": 0,
        "matchScore": 0,
        "poseTimeRemaining": 0,
        "sessionElapsed": 0,
        "isFormGood": False,
        "queue": []
    })


class WebSocketManager:
    """Manages WebSocket connections and yoga session rooms."""

    def __init__(self):
        self.rooms: Dict[str, YogaRoom] = {}
        self.cleanup_task: Optional[asyncio.Task] = None

    def generate_room_code(self) -> str:
        """Generate a unique 4-digit room code."""
        while True:
            code = ''.join(random.choices(string.digits, k=4))
            if code not in self.rooms:
                return code

    def create_room(self) -> str:
        """Create a new room and return its code."""
        code = self.generate_room_code()
        self.rooms[code] = YogaRoom(
            code=code,
            created_at=datetime.now()
        )
        return code

    def get_room(self, code: str) -> Optional[YogaRoom]:
        """Get a room by its code."""
        return self.rooms.get(code)

    def room_exists(self, code: str) -> bool:
        """Check if a room exists."""
        return code in self.rooms

    async def connect_desktop(self, websocket: WebSocket, code: str) -> bool:
        """Connect desktop client to a room."""
        room = self.rooms.get(code)
        if not room:
            return False

        await websocket.accept()
        room.desktop = websocket

        # Notify remotes that desktop connected
        await self.broadcast_to_remotes(code, {
            "type": "desktop_connected"
        })

        return True

    async def connect_remote(self, websocket: WebSocket, code: str) -> bool:
        """Connect remote (phone) client to a room."""
        room = self.rooms.get(code)
        if not room:
            print(f"[WS] Remote tried to connect to non-existent room: {code}")
            return False

        await websocket.accept()
        room.remotes.add(websocket)
        print(f"[WS] Remote connected to room {code}, current state: {room.state.get('status')}", flush=True)

        # Send current state to the new remote
        await websocket.send_json({
            "type": "state_sync",
            "state": room.state
        })

        return True

    async def disconnect(self, websocket: WebSocket, code: str):
        """Handle client disconnection."""
        room = self.rooms.get(code)
        if not room:
            return

        if room.desktop == websocket:
            room.desktop = None
            # Notify remotes that desktop disconnected
            await self.broadcast_to_remotes(code, {
                "type": "desktop_disconnected"
            })
        elif websocket in room.remotes:
            room.remotes.discard(websocket)

        # Clean up empty rooms
        if room.desktop is None and len(room.remotes) == 0:
            del self.rooms[code]

    async def handle_desktop_message(self, code: str, message: dict):
        """Handle message from desktop client."""
        room = self.rooms.get(code)
        if not room:
            return

        msg_type = message.get("type")

        if msg_type == "state_update":
            # Update room state and broadcast to remotes
            state_data = message.get("state", {})
            old_status = room.state.get("status")
            room.state.update(state_data)
            new_status = room.state.get("status")
            if old_status != new_status:
                print(f"[WS] Room {code} state changed: {old_status} -> {new_status}")
            await self.broadcast_to_remotes(code, {
                "type": "state_sync",
                "state": room.state
            })

        elif msg_type == "pose_change":
            # Broadcast pose change to remotes
            room.state["currentPose"] = message.get("pose")
            room.state["poseIndex"] = message.get("index", 0)
            room.state["poseTimeRemaining"] = message.get("duration", 0)
            await self.broadcast_to_remotes(code, {
                "type": "pose_change",
                "pose": message.get("pose"),
                "index": message.get("index"),
                "duration": message.get("duration")
            })

    async def handle_remote_message(self, code: str, message: dict):
        """Handle message from remote (phone) client."""
        room = self.rooms.get(code)
        if not room:
            print(f"[WS] Remote message for unknown room: {code}")
            return
        if not room.desktop:
            print(f"[WS] Remote message but no desktop connected: {code}")
            return

        msg_type = message.get("type")
        print(f"[WS] Remote message: type={msg_type}, full={message}", flush=True)

        # Handle command type messages (from remote)
        if msg_type == "command":
            command = message.get("command")
            print(f"[WS] Command received: {command}", flush=True)
            if command in ["start", "pause", "resume", "skip", "end", "toggle_voice", "toggle_ambient"]:
                try:
                    await room.desktop.send_json({
                        "type": "command",
                        "command": command
                    })
                    print(f"[WS] Forwarded command to desktop: {command}", flush=True)
                except Exception as e:
                    print(f"[WS] Error forwarding command: {e}", flush=True)
            return

        # Legacy: Forward direct commands to desktop (for backwards compatibility)
        if msg_type in ["start", "pause", "resume", "skip", "end", "toggle_voice", "toggle_ambient"]:
            try:
                await room.desktop.send_json({
                    "type": "command",
                    "command": msg_type
                })
            except Exception:
                pass

        # Forward volume controls to desktop
        if msg_type in ["voice_volume", "ambient_volume"]:
            try:
                await room.desktop.send_json({
                    "type": msg_type,
                    "value": message.get("value", 50)
                })
            except Exception:
                pass

        # Forward ambient track selection to desktop
        if msg_type == "ambient_track":
            try:
                await room.desktop.send_json({
                    "type": "ambient_track",
                    "track": message.get("track", "forest")
                })
            except Exception:
                pass

    async def broadcast_to_remotes(self, code: str, message: dict):
        """Send message to all remote clients in a room."""
        room = self.rooms.get(code)
        if not room:
            return

        disconnected = set()
        for remote in room.remotes:
            try:
                await remote.send_json(message)
            except Exception:
                disconnected.add(remote)

        # Clean up disconnected remotes
        room.remotes -= disconnected

    async def cleanup_old_rooms(self):
        """Remove rooms older than 2 hours."""
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            cutoff = datetime.now() - timedelta(hours=2)
            expired = [
                code for code, room in self.rooms.items()
                if room.created_at < cutoff
            ]
            for code in expired:
                room = self.rooms.pop(code, None)
                if room:
                    # Close all connections
                    if room.desktop:
                        try:
                            await room.desktop.close()
                        except Exception:
                            pass
                    for remote in room.remotes:
                        try:
                            await remote.close()
                        except Exception:
                            pass

    def start_cleanup_task(self):
        """Start the background cleanup task."""
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self.cleanup_old_rooms())


# Global instance
ws_manager = WebSocketManager()
