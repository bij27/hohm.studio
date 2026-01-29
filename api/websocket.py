from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import math
import time
from datetime import datetime
from typing import Dict, Optional
from core.posture_analyzer import PostureAnalyzer
from core.calibration import Calibrator
from services.session_manager import SessionManager
from models.schemas import CalibrationProfile, PostureStatus
from models.database import save_session, save_log
from middleware.auth import validate_token_format
from middleware.security import validate_websocket_origin
import config as cfg

router = APIRouter()

# Constants
MAX_LOGS_PER_SESSION = 10000  # Prevent storage abuse
WEBSOCKET_TIMEOUT = 60.0  # Seconds to wait for message
MAX_MESSAGE_SIZE = 65536  # 64KB max message size
MAX_LANDMARKS_SIZE = 33  # MediaPipe has 33 pose landmarks
MAX_PROFILE_SIZE = 10000  # 10KB max profile JSON size


def _debug_log(message: str):
    """Print debug message only in development environment."""
    if cfg.ENVIRONMENT == "development":
        print(message)


# === RATE LIMITER ===

class RateLimiter:
    """Simple rate limiter to prevent message spam."""
    def __init__(self, max_messages: int = 10, window_seconds: float = 1.0):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.messages: list = []

    def is_allowed(self) -> bool:
        """Returns True if message is allowed, False if rate limited."""
        now = time.time()
        # Remove old messages outside the window
        self.messages = [t for t in self.messages if now - t < self.window_seconds]

        if len(self.messages) >= self.max_messages:
            return False

        self.messages.append(now)
        return True


# === UTILITY FUNCTIONS ===

def parse_landmarks(raw_landmarks: Dict) -> Dict[int, Dict]:
    """Convert string-keyed landmark dict to int-keyed dict expected by analyzer."""
    # Validate input size to prevent DoS
    if not isinstance(raw_landmarks, dict) or len(raw_landmarks) > MAX_LANDMARKS_SIZE * 2:
        return {}

    landmarks = {}
    for i in range(MAX_LANDMARKS_SIZE):  # MediaPipe has 33 pose landmarks
        key = str(i)
        if key in raw_landmarks:
            lm = raw_landmarks[key]
            # Validate landmark structure and values
            if isinstance(lm, dict) and 'x' in lm and 'y' in lm:
                try:
                    x = float(lm['x'])
                    y = float(lm['y'])
                    # Coordinates should be normalized 0-1 or reasonable pixel values
                    if -10 <= x <= 10 and -10 <= y <= 10:
                        landmarks[i] = {'x': x, 'y': y}
                        # Include optional z and visibility if present
                        if 'z' in lm:
                            landmarks[i]['z'] = float(lm['z'])
                        if 'visibility' in lm:
                            landmarks[i]['visibility'] = float(lm['visibility'])
                except (ValueError, TypeError):
                    continue
    return landmarks


def validate_score(value) -> float:
    """Validate and sanitize score value, handling NaN/Infinity."""
    try:
        score = float(value) if value is not None else 0.0
        # Check for NaN or Infinity
        if math.isnan(score) or math.isinf(score):
            return 0.0
        return max(0.0, min(10.0, score))
    except (ValueError, TypeError):
        return 0.0


# === CONNECTION LIMITER ===

class ConnectionLimiter:
    """Limits concurrent WebSocket connections per IP to prevent resource exhaustion."""

    def __init__(self, max_per_ip: int = 5):
        self.max_per_ip = max_per_ip
        self.connections: Dict[str, int] = {}

    def _get_client_ip(self, websocket: WebSocket) -> str:
        """Extract client IP from WebSocket connection."""
        # Check forwarded headers (from reverse proxy)
        forwarded = websocket.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = websocket.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
        # Direct connection
        if websocket.client:
            return websocket.client.host
        return "unknown"

    def can_connect(self, websocket: WebSocket) -> bool:
        """Check if a new connection is allowed for this IP."""
        ip = self._get_client_ip(websocket)
        current = self.connections.get(ip, 0)
        return current < self.max_per_ip

    def add_connection(self, websocket: WebSocket) -> str:
        """Track a new connection. Returns the IP."""
        ip = self._get_client_ip(websocket)
        self.connections[ip] = self.connections.get(ip, 0) + 1
        return ip

    def remove_connection(self, ip: str):
        """Remove a connection from tracking."""
        if ip in self.connections:
            self.connections[ip] -= 1
            if self.connections[ip] <= 0:
                del self.connections[ip]


# Global connection limiter
connection_limiter = ConnectionLimiter(max_per_ip=5)


# === WEBSOCKET ENDPOINT ===

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Validate origin before accepting connection
    if not validate_websocket_origin(websocket):
        await websocket.close(code=4000, reason="Connection rejected")
        return

    # Check connection limit per IP
    if not connection_limiter.can_connect(websocket):
        await websocket.close(code=4000, reason="Connection rejected")
        return

    await websocket.accept()
    client_ip = connection_limiter.add_connection(websocket)

    # Profile is now stored client-side (localStorage)
    # We receive it from the client when they connect or after calibration
    profile: Optional[CalibrationProfile] = None
    analyzer = PostureAnalyzer(profile)
    calibrator = Calibrator()
    session_manager = SessionManager()
    audio_enabled = True
    rate_limiter = RateLimiter(max_messages=15, window_seconds=1.0)
    session_saved = False  # Flag to prevent double-save
    device_token: Optional[str] = None  # Device token for session ownership

    try:
        while True:
            # Add timeout to prevent blocking forever
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=WEBSOCKET_TIMEOUT
                )
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
                continue

            # Message size limit - prevent memory exhaustion attacks
            if len(data) > MAX_MESSAGE_SIZE:
                continue

            # Rate limiting - skip processing if too many messages
            if not rate_limiter.is_allowed():
                continue

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            # Validate action field
            action = message.get('action')
            if not action or not isinstance(action, str) or len(action) > 50:
                continue

            if action == 'set_device_token':
                # Client sends their device token for session ownership
                token = message.get('token')
                if token and validate_token_format(token):
                    device_token = token
                    await websocket.send_json({
                        "type": "device_token_set",
                        "data": {"success": True}
                    })
                else:
                    await websocket.send_json({
                        "type": "device_token_set",
                        "data": {"success": False, "error": "Invalid token format"}
                    })

            elif action == 'set_profile':
                # Client sends their stored profile on connect
                profile_data = message.get('profile')
                if profile_data:
                    # Validate profile size to prevent memory exhaustion
                    profile_str = json.dumps(profile_data) if isinstance(profile_data, dict) else str(profile_data)
                    if len(profile_str) > MAX_PROFILE_SIZE:
                        await websocket.send_json({
                            "type": "profile_loaded",
                            "data": {"success": False, "error": "Profile data too large"}
                        })
                        continue

                    try:
                        profile = CalibrationProfile(**profile_data)
                        analyzer.profile = profile
                        await websocket.send_json({
                            "type": "profile_loaded",
                            "data": {"success": True}
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "type": "profile_loaded",
                            "data": {"success": False, "error": "Invalid profile data"}
                        })

            elif action == 'calibrate_landmarks':
                raw_landmarks = message.get('landmarks', {})
                if not raw_landmarks:
                    await websocket.send_json({
                        "type": "calibration_warning",
                        "data": {"message": "No landmarks detected"}
                    })
                    continue

                landmarks = parse_landmarks(raw_landmarks)
                if not landmarks:
                    await websocket.send_json({
                        "type": "calibration_warning",
                        "data": {"message": "Invalid landmark data"}
                    })
                    continue

                try:
                    is_collecting, instruction = calibrator.add_frame(landmarks)

                    if calibrator.is_complete():
                        new_profile = calibrator.finalize()
                        analyzer.profile = new_profile
                        profile = new_profile
                        # Send profile to client to store in localStorage
                        await websocket.send_json({
                            "type": "calibration_complete",
                            "data": {"profile": json.loads(new_profile.json())}
                        })
                    else:
                        await websocket.send_json({
                            "type": "calibration_progress",
                            "data": {
                                "instruction": instruction,
                                "is_collecting": is_collecting,
                                "count": len(calibrator.collected_landmarks),
                                "total": calibrator.num_required_frames
                            }
                        })
                except Exception as e:
                    # Sanitize error message in production to avoid information leakage
                    error_msg = str(e) if cfg.ENVIRONMENT == "development" else "Processing error"
                    await websocket.send_json({
                        "type": "calibration_warning",
                        "data": {"message": f"Calibration error: {error_msg}"}
                    })

            elif action == 'process_landmarks':
                raw_landmarks = message.get('landmarks', {})
                if not raw_landmarks or not session_manager.is_active:
                    continue

                landmarks = parse_landmarks(raw_landmarks)
                if not landmarks:
                    continue

                metrics, score, issues = analyzer.analyze(landmarks)
                score = validate_score(score)  # Sanitize score
                status_str = analyzer.get_status_with_hysteresis(score)
                status = PostureStatus.BAD if status_str == "bad" else PostureStatus.WARNING if status_str == "warning" else PostureStatus.GOOD
                session_manager.update_stats(status, score)

                should_alert, play_sound = analyzer.check_alert_condition(score)
                if should_alert:
                    await websocket.send_json({
                        "type": "alert",
                        "data": {
                            "message": issues[0].advice if issues else "Poor posture detected",
                            "play_sound": play_sound and audio_enabled
                        }
                    })

                await websocket.send_json({
                    "type": "metrics",
                    "data": {
                        "status": status,
                        "score": round(score, 1),
                        "current_issues": [issue.dict() for issue in issues],
                        "session_stats": {
                            "good_time_minutes": round(session_manager.good_time_sec / 60.0, 1),
                            "bad_time_minutes": round(session_manager.bad_time_sec / 60.0, 1)
                        }
                    }
                })

            elif action == 'start_session':
                session_id = session_manager.start()
                session_saved = False  # Reset flag for new session
                _debug_log(f"[SESSION] Started: {session_id}")
                await websocket.send_json({"type": "session_started", "data": {"session_id": session_id}})

            elif action == 'stop_session':
                if session_saved:
                    continue  # Already saved, skip

                summary = session_manager.stop()
                summary['end_time'] = datetime.now()
                summary['total_logs'] = min(session_manager.log_count, MAX_LOGS_PER_SESSION)
                summary['start_time'] = session_manager.start_time

                # Save with validation and device token for ownership
                success, error = await save_session(summary, device_token)
                session_saved = True  # Mark as saved to prevent double-save

                if not success:
                    summary['save_error'] = error
                    _debug_log(f"[SESSION] Save failed: {error}")
                else:
                    _debug_log(f"[SESSION] Saved: {summary.get('session_id')}")

                await websocket.send_json({"type": "session_stopped", "data": summary})

            elif action == 'toggle_audio':
                audio_enabled = message.get('enabled', True)

            elif action == 'update_session_stats':
                # Receive accurate timing from frontend
                if session_manager.is_active:
                    good_time = message.get('good_time_sec', 0)
                    bad_time = message.get('bad_time_sec', 0)
                    # Validate timing values
                    if isinstance(good_time, (int, float)) and not math.isnan(good_time):
                        session_manager.good_time_sec = max(0, good_time)
                    if isinstance(bad_time, (int, float)) and not math.isnan(bad_time):
                        session_manager.bad_time_sec = max(0, bad_time)

            elif action == 'log_posture':
                # Log posture data (without screenshots)
                if not session_manager.is_active:
                    continue

                # Enforce max logs limit
                if session_manager.log_count >= MAX_LOGS_PER_SESSION:
                    continue

                # Validate and sanitize inputs
                score = validate_score(message.get('score', 0))

                status = message.get('status', 'bad')
                if status not in ('good', 'warning', 'bad'):
                    status = 'bad'

                # Validate issues array
                raw_issues = message.get('issues', [])
                issues = []
                if isinstance(raw_issues, list):
                    for issue in raw_issues[:10]:  # Limit to 10 issues
                        if isinstance(issue, dict):
                            # Only keep expected fields, sanitize strings
                            clean_issue = {
                                'type': str(issue.get('type', ''))[:50],
                                'severity': str(issue.get('severity', ''))[:20],
                                'advice': str(issue.get('advice', ''))[:200]
                            }
                            issues.append(clean_issue)

                # Save log entry
                log_data = {
                    "session_id": session_manager.session_id,
                    "timestamp": datetime.now(),
                    "status": status,
                    "score": score,
                    "issues": issues,
                    "metrics": {}
                }
                success, error = await save_log(log_data)
                if success:
                    session_manager.log_count += 1
                else:
                    _debug_log(f"[LOG] Save failed: {error}")

            elif action == 'pong':
                # Response to our ping, connection is alive
                pass

    except WebSocketDisconnect:
        _debug_log("[WS] Client disconnected")
    except Exception as e:
        _debug_log(f"[WS] Connection error: {e}")
    finally:
        # Always release connection slot
        connection_limiter.remove_connection(client_ip)

    # Auto-save session if it was active and not already saved
    if session_manager.is_active and not session_saved:
        try:
            _debug_log(f"[SESSION] Auto-saving: {session_manager.session_id}")
            summary = session_manager.stop()
            summary['end_time'] = datetime.now()
            summary['total_logs'] = min(session_manager.log_count, MAX_LOGS_PER_SESSION)
            summary['start_time'] = session_manager.start_time

            success, error = await save_session(summary, device_token)
            if success:
                _debug_log(f"[SESSION] Auto-saved: {summary.get('session_id')}")
            else:
                _debug_log(f"[SESSION] Auto-save failed: {error}")
        except Exception as e:
            _debug_log(f"[SESSION] Auto-save error: {e}")
