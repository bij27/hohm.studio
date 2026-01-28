from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import os
import time
from datetime import datetime
from typing import Dict, Optional
from core.posture_analyzer import PostureAnalyzer
from core.calibration import Calibrator
from services.session_manager import SessionManager
from models.schemas import CalibrationProfile, PostureStatus
from models.database import save_session, save_log

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

    # Profile is now stored client-side (localStorage)
    # We receive it from the client when they connect or after calibration
    profile: Optional[CalibrationProfile] = None
    analyzer = PostureAnalyzer(profile)
    calibrator = Calibrator()
    session_manager = SessionManager()
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
                # Log posture data (without screenshots)
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

                # Save log entry (no screenshot)
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
