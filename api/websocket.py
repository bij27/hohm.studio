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

router = APIRouter()

# Constants
MAX_LOGS_PER_SESSION = 10000  # Prevent storage abuse
WEBSOCKET_TIMEOUT = 60.0  # Seconds to wait for message


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
    landmarks = {}
    for i in range(33):  # MediaPipe has 33 pose landmarks
        key = str(i)
        if key in raw_landmarks:
            lm = raw_landmarks[key]
            # Basic validation
            if isinstance(lm, dict) and 'x' in lm and 'y' in lm:
                landmarks[i] = lm
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


# === WEBSOCKET ENDPOINT ===

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Profile is now stored client-side (localStorage)
    # We receive it from the client when they connect or after calibration
    profile: Optional[CalibrationProfile] = None
    analyzer = PostureAnalyzer(profile)
    calibrator = Calibrator()
    session_manager = SessionManager()
    audio_enabled = True
    rate_limiter = RateLimiter(max_messages=15, window_seconds=1.0)
    session_saved = False  # Flag to prevent double-save

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

            # Rate limiting - skip processing if too many messages
            if not rate_limiter.is_allowed():
                continue

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                continue

            action = message.get('action')

            if action == 'set_profile':
                # Client sends their stored profile on connect
                profile_data = message.get('profile')
                if profile_data:
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
                            "data": {"success": False, "error": str(e)}
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
                    await websocket.send_json({
                        "type": "calibration_warning",
                        "data": {"message": f"Calibration error: {str(e)}"}
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
                print(f"[SESSION] Started new session: {session_id}")
                await websocket.send_json({"type": "session_started", "data": {"session_id": session_id}})

            elif action == 'stop_session':
                if session_saved:
                    continue  # Already saved, skip

                summary = session_manager.stop()
                summary['end_time'] = datetime.now()
                summary['total_logs'] = min(session_manager.log_count, MAX_LOGS_PER_SESSION)
                summary['start_time'] = session_manager.start_time

                # Save with validation
                success, error = await save_session(summary)
                session_saved = True  # Mark as saved to prevent double-save

                if not success:
                    summary['save_error'] = error
                    print(f"[SESSION] Save failed: {error}")
                else:
                    print(f"[SESSION] Saved: {summary.get('session_id')}")

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
                    print(f"[LOG] Failed to save: {error}")

            elif action == 'pong':
                # Response to our ping, connection is alive
                pass

    except WebSocketDisconnect:
        print("[WS] Client disconnected normally")
    except Exception as e:
        print(f"[WS] Connection error: {e}")

    # Auto-save session if it was active and not already saved
    if session_manager.is_active and not session_saved:
        try:
            print(f"[SESSION] Auto-saving active session: {session_manager.session_id}")
            summary = session_manager.stop()
            summary['end_time'] = datetime.now()
            summary['total_logs'] = min(session_manager.log_count, MAX_LOGS_PER_SESSION)
            summary['start_time'] = session_manager.start_time

            success, error = await save_session(summary)
            if success:
                print(f"[SESSION] Auto-saved: {summary.get('session_id')}")
            else:
                print(f"[SESSION] Auto-save failed: {error}")
        except Exception as e:
            print(f"[SESSION] Failed to auto-save: {e}")
