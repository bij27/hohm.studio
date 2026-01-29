"""
WebSocket Manager for Yoga Session Remote Control

Handles real-time communication between desktop browser and phone remote.
Security: Uses cryptographic tokens for QR pairing + rate-limited fallback codes.
"""

import asyncio
import secrets
import string
from typing import Dict, Set, Optional
from fastapi import WebSocket
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import time
import config as cfg


def _debug_log(message: str):
    """Print debug message only in development environment."""
    if cfg.ENVIRONMENT == "development":
        print(message)


@dataclass
class YogaRoom:
    """Represents a yoga session room with connected clients."""
    code: str  # 6-char alphanumeric fallback code
    token: str  # 64-char cryptographic token for QR
    created_at: datetime
    token_used: bool = False  # Token is single-use
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


# Rate limiter for code-based joins (prevents brute force)
class CodeRateLimiter:
    """Rate limiter specifically for room code attempts."""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60, block_seconds: int = 300):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self.attempts: Dict[str, list] = {}  # ip -> [timestamps]
        self.blocked: Dict[str, float] = {}  # ip -> unblock_time

    def is_blocked(self, ip: str) -> tuple[bool, int]:
        """Check if IP is blocked. Returns (is_blocked, seconds_remaining)."""
        if ip in self.blocked:
            remaining = self.blocked[ip] - time.time()
            if remaining > 0:
                return True, int(remaining)
            del self.blocked[ip]
        return False, 0

    def record_attempt(self, ip: str, success: bool) -> None:
        """Record a code attempt. Block IP if too many failures."""
        if success:
            # Clear attempts on success
            self.attempts.pop(ip, None)
            return

        now = time.time()
        if ip not in self.attempts:
            self.attempts[ip] = []

        # Clean old attempts
        self.attempts[ip] = [t for t in self.attempts[ip] if now - t < self.window_seconds]
        self.attempts[ip].append(now)

        # Block if too many attempts
        if len(self.attempts[ip]) >= self.max_attempts:
            self.blocked[ip] = now + self.block_seconds
            self.attempts.pop(ip, None)


# Global rate limiter for room codes
code_rate_limiter = CodeRateLimiter()


class WebSocketManager:
    """Manages WebSocket connections and yoga session rooms."""

    # Room expiry time (prevents abandoned rooms from accumulating)
    ROOM_EXPIRY_MINUTES = 120  # 2 hours
    TOKEN_EXPIRY_MINUTES = 5   # Token valid for 5 minutes

    def __init__(self):
        self.rooms: Dict[str, YogaRoom] = {}  # code -> room
        self.tokens: Dict[str, str] = {}  # token -> code (for quick token lookup)
        self.cleanup_task: Optional[asyncio.Task] = None

    def _generate_code(self) -> str:
        """Generate a unique 6-character alphanumeric room code (uppercase for readability)."""
        alphabet = string.ascii_uppercase + string.digits
        # Remove ambiguous characters (0, O, I, 1, L) for better UX
        alphabet = alphabet.replace('0', '').replace('O', '').replace('I', '').replace('1', '').replace('L', '')
        while True:
            code = ''.join(secrets.choice(alphabet) for _ in range(6))
            if code not in self.rooms:
                return code

    def _generate_token(self) -> str:
        """Generate a cryptographically secure 64-character token for QR codes."""
        return secrets.token_urlsafe(48)  # 48 bytes = 64 chars in base64

    def create_room(self) -> dict:
        """Create a new room and return its code and token."""
        code = self._generate_code()
        token = self._generate_token()

        self.rooms[code] = YogaRoom(
            code=code,
            token=token,
            created_at=datetime.now()
        )
        self.tokens[token] = code

        return {
            "code": code,
            "token": token
        }

    def get_room(self, code: str) -> Optional[YogaRoom]:
        """Get a room by its code."""
        return self.rooms.get(code)

    def get_room_by_token(self, token: str) -> Optional[YogaRoom]:
        """Get a room by its token (for QR code joins)."""
        code = self.tokens.get(token)
        if not code:
            return None
        return self.rooms.get(code)

    def validate_token(self, token: str) -> tuple[Optional[YogaRoom], str]:
        """
        Validate a token for QR-based joining.
        Returns (room, error_message). Room is None if invalid.
        """
        room = self.get_room_by_token(token)

        if not room:
            return None, "Invalid or expired link"

        # Check if token already used
        if room.token_used:
            return None, "This link has already been used. Please scan a new QR code."

        # Check if token expired (5 minute window)
        age = datetime.now() - room.created_at
        if age > timedelta(minutes=self.TOKEN_EXPIRY_MINUTES):
            return None, "This link has expired. Please scan a new QR code."

        # Mark token as used (single-use)
        room.token_used = True

        return room, ""

    def validate_code(self, code: str, client_ip: str) -> tuple[Optional[YogaRoom], str]:
        """
        Validate a room code for manual entry.
        Includes rate limiting. Returns (room, error_message).
        """
        # Check if IP is blocked
        is_blocked, remaining = code_rate_limiter.is_blocked(client_ip)
        if is_blocked:
            return None, f"Too many attempts. Please wait {remaining} seconds."

        # Normalize code (uppercase, strip whitespace)
        code = code.strip().upper()

        # Validate format (6 alphanumeric)
        if not code or len(code) != 6 or not code.isalnum():
            code_rate_limiter.record_attempt(client_ip, success=False)
            return None, "Invalid code format"

        room = self.rooms.get(code)
        if not room:
            code_rate_limiter.record_attempt(client_ip, success=False)
            return None, "Room not found. Check the code and try again."

        # Success - clear rate limit counter
        code_rate_limiter.record_attempt(client_ip, success=True)
        return room, ""

    def room_exists(self, code: str) -> bool:
        """Check if a room exists by code."""
        return code.strip().upper() in self.rooms

    async def connect_desktop(self, websocket: WebSocket, code: str) -> bool:
        """Connect desktop client to a room."""
        code = code.strip().upper()
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
        code = code.strip().upper()
        room = self.rooms.get(code)
        if not room:
            _debug_log(f"[WS] Remote tried to connect to non-existent room: {code}")
            return False

        await websocket.accept()
        room.remotes.add(websocket)
        _debug_log(f"[WS] Remote connected to room {code}")

        # Send current state to the new remote
        await websocket.send_json({
            "type": "state_sync",
            "state": room.state
        })

        return True

    async def disconnect(self, websocket: WebSocket, code: str):
        """Handle client disconnection."""
        code = code.strip().upper()
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
            # Remove token mapping
            if room.token in self.tokens:
                del self.tokens[room.token]
            del self.rooms[code]

    async def handle_desktop_message(self, code: str, message: dict):
        """Handle message from desktop client."""
        code = code.strip().upper()
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
                _debug_log(f"[WS] Room {code}: {old_status} -> {new_status}")
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
        code = code.strip().upper()
        room = self.rooms.get(code)
        if not room:
            _debug_log(f"[WS] Remote message for unknown room: {code}")
            return
        if not room.desktop:
            _debug_log(f"[WS] Remote message but no desktop: {code}")
            return

        msg_type = message.get("type")

        # Handle command type messages (from remote)
        if msg_type == "command":
            command = message.get("command")
            _debug_log(f"[WS] Command: {command}")
            if command in ["start", "pause", "resume", "skip", "end", "toggle_voice", "toggle_ambient"]:
                try:
                    await room.desktop.send_json({
                        "type": "command",
                        "command": command
                    })
                    _debug_log(f"[WS] Forwarded: {command}")
                except Exception as e:
                    _debug_log(f"[WS] Forward error: {e}")
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
        code = code.strip().upper()
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
        """Remove rooms older than configured expiry time."""
        while True:
            await asyncio.sleep(300)  # Check every 5 minutes
            cutoff = datetime.now() - timedelta(minutes=self.ROOM_EXPIRY_MINUTES)
            expired = [
                code for code, room in self.rooms.items()
                if room.created_at < cutoff
            ]
            for code in expired:
                room = self.rooms.pop(code, None)
                if room:
                    # Remove token mapping
                    if room.token in self.tokens:
                        del self.tokens[room.token]
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
