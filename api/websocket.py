from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import os
import time
import base64
from datetime import datetime
from typing import Dict, Optional
from core.posture_analyzer import PostureAnalyzer
from core.calibration import Calibrator
from services.session_manager import SessionManager
from services.logger import PostureLogger
from models.schemas import CalibrationProfile, PostureStatus
from models.database import save_session, save_log
import config as cfg

router = APIRouter()


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

def load_profile() -> Optional[CalibrationProfile]:
    """Load calibration profile from disk if it exists.

    If the profile is corrupted (invalid JSON or missing required fields),
    it is automatically deleted to allow fresh calibration.
    """
    if not os.path.exists(cfg.PROFILE_PATH):
        return None
    try:
        with open(cfg.PROFILE_PATH, "r") as f:
            data = json.load(f)
            return CalibrationProfile(**data)
    except (json.JSONDecodeError, TypeError, KeyError, ValueError) as e:
        # Profile is corrupted - delete it so user can recalibrate
        try:
            os.remove(cfg.PROFILE_PATH)
            print(f"[PROFILE] Deleted corrupted profile: {e}")
        except OSError:
            pass
        return None
    except Exception:
        return None


def save_profile(profile: CalibrationProfile) -> bool:
    """Save calibration profile to disk. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(cfg.PROFILE_PATH), exist_ok=True)
        with open(cfg.PROFILE_PATH, "w") as f:
            f.write(profile.json())
        return True
    except Exception:
        return False


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


# === WEBSOCKET ENDPOINT ===

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    profile = load_profile()
    analyzer = PostureAnalyzer(profile)
    calibrator = Calibrator()
    session_manager = SessionManager()
    logger = None
    audio_enabled = True
    rate_limiter = RateLimiter(max_messages=15, window_seconds=1.0)  # 15 msgs/sec max

    try:
        while True:
            data = await websocket.receive_text()

            # Rate limiting - skip processing if too many messages
            if not rate_limiter.is_allowed():
                continue

            message = json.loads(data)
            action = message.get('action')

            if action == 'calibrate_landmarks':
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
                        save_profile(new_profile)
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
                logger = PostureLogger(session_id)
                print(f"[SESSION] Started new session: {session_id}")
                await websocket.send_json({"type": "session_started", "data": {"session_id": session_id}})

            elif action == 'stop_session':
                summary = session_manager.stop()
                summary['end_time'] = datetime.now()
                summary['total_logs'] = session_manager.log_count
                summary['start_time'] = session_manager.start_time

                # Save with validation - returns (success, error_message)
                success, error = await save_session(summary)
                if not success:
                    summary['save_error'] = error

                await websocket.send_json({"type": "session_stopped", "data": summary})

            elif action == 'toggle_audio':
                audio_enabled = message.get('enabled', True)

            elif action == 'update_session_stats':
                # Receive accurate timing from frontend
                if session_manager.is_active:
                    session_manager.good_time_sec = message.get('good_time_sec', 0)
                    session_manager.bad_time_sec = message.get('bad_time_sec', 0)
                    print(f"[SESSION] Updated stats from frontend - Good: {session_manager.good_time_sec:.1f}s, Bad: {session_manager.bad_time_sec:.1f}s")

            elif action == 'log_posture':
                # Receive screenshot and log from frontend
                if not session_manager.is_active:
                    continue

                # Validate and sanitize inputs
                try:
                    score = float(message.get('score', 0))
                    score = max(0.0, min(10.0, score))  # Clamp to valid range
                except (ValueError, TypeError):
                    score = 0.0

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

                screenshot_b64 = message.get('screenshot', '')

                screenshot_path = ''
                if screenshot_b64 and isinstance(screenshot_b64, str) and screenshot_b64.startswith('data:image'):
                    try:
                        # Validate image format
                        if not screenshot_b64.startswith('data:image/jpeg') and not screenshot_b64.startswith('data:image/png'):
                            raise ValueError("Invalid image format - only JPEG and PNG allowed")

                        # Check size limit before decoding
                        if len(screenshot_b64) > cfg.MAX_SCREENSHOT_SIZE_BYTES * 1.4:  # Base64 is ~1.33x larger
                            raise ValueError(f"Screenshot too large (max {cfg.MAX_UPLOAD_SIZE_MB}MB)")

                        # Ensure screenshot directory exists
                        os.makedirs(cfg.SCREENSHOT_DIR, exist_ok=True)

                        # Decode base64 image
                        header, data = screenshot_b64.split(',', 1)
                        image_data = base64.b64decode(data)

                        # Verify decoded size
                        if len(image_data) > cfg.MAX_SCREENSHOT_SIZE_BYTES:
                            raise ValueError("Decoded image too large")

                        # Validate filename components (prevent path traversal)
                        session_id = session_manager.session_id
                        if not session_id or '..' in session_id or '/' in session_id or '\\' in session_id:
                            raise ValueError("Invalid session ID")

                        # Save to file with safe filename
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        filename = f"{session_id}_{timestamp}.jpg"
                        screenshot_path = os.path.join(cfg.SCREENSHOT_DIR, filename)

                        # Ensure we're writing within the screenshot directory
                        real_path = os.path.realpath(screenshot_path)
                        real_dir = os.path.realpath(cfg.SCREENSHOT_DIR)
                        if not real_path.startswith(real_dir):
                            raise ValueError("Invalid file path")

                        with open(screenshot_path, 'wb') as f:
                            f.write(image_data)
                        print(f"[SCREENSHOT] Saved: {filename}")
                    except Exception as e:
                        print(f"[SCREENSHOT] Failed to save: {e}")
                        screenshot_path = ''

                # Save log entry
                log_data = {
                    "session_id": session_manager.session_id,
                    "timestamp": datetime.now(),
                    "status": status,
                    "score": score,
                    "issues": issues,
                    "metrics": {},
                    "screenshot_path": screenshot_path
                }
                success, error = await save_log(log_data)
                if success:
                    session_manager.log_count += 1
                    print(f"[LOG] Saved posture log, score={score}")
                else:
                    print(f"[LOG] Failed to save: {error}")

    except WebSocketDisconnect:
        print("[WS] Client disconnected normally")
    except Exception as e:
        print(f"[WS] Connection error: {e}")

    # Auto-save session if it was active when connection closed (runs after try/except)
    if session_manager.is_active:
        try:
            print(f"[SESSION] Auto-saving active session: {session_manager.session_id}")
            summary = session_manager.stop()
            summary['end_time'] = datetime.now()
            summary['total_logs'] = session_manager.log_count
            summary['start_time'] = session_manager.start_time

            # Save session - await properly
            success, error = await save_session(summary)
            if success:
                print(f"[SESSION] Auto-saved successfully: {summary.get('session_id', 'unknown')} - Grade: {summary.get('average_score')}, Good: {summary.get('good_posture_percentage')}%")
            else:
                print(f"[SESSION] Auto-save failed: {error}")
        except Exception as e:
            print(f"[SESSION] Failed to auto-save: {e}")
    else:
        print("[WS] No active session to save")

    # Cleanup resources
    if logger:
        logger = None
