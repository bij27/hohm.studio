import os
import cv2
from datetime import datetime
import config as cfg
from models.database import save_log

# Maximum screenshots to keep (retention policy)
MAX_SCREENSHOTS = 50


class PostureLogger:
    """
    Handles logging of posture events and saving screenshots.
    Includes automatic cleanup of old screenshots.
    """
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.last_log_time = None
        self.log_interval = 30  # seconds

    async def log_if_needed(self, frame, status, score, issues, metrics):
        now = datetime.now()
        if self.last_log_time is None or (now - self.last_log_time).total_seconds() >= self.log_interval:
            self.last_log_time = now

            # Save screenshot
            filename = f"{self.session_id}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
            filepath = os.path.join(cfg.SCREENSHOT_DIR, filename)

            # Add annotations to the screenshot
            annotated_frame = frame.copy()
            cv2.putText(annotated_frame, f"Score: {score}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
            cv2.putText(annotated_frame, f"Status: {status}", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            cv2.imwrite(filepath, annotated_frame)

            # Cleanup old screenshots (retention policy)
            self._cleanup_old_screenshots()

            log_data = {
                "session_id": self.session_id,
                "timestamp": now,
                "status": status,
                "score": score,
                "issues": [issue.dict() for issue in issues],
                "metrics": metrics.dict(),
                "screenshot_path": filepath
            }

            await save_log(log_data)
            return True
        return False

    def _cleanup_old_screenshots(self):
        """Remove oldest screenshots if we exceed MAX_SCREENSHOTS."""
        try:
            if not os.path.exists(cfg.SCREENSHOT_DIR):
                return

            # Get all jpg files with their modification times
            files = []
            for f in os.listdir(cfg.SCREENSHOT_DIR):
                if f.endswith('.jpg'):
                    path = os.path.join(cfg.SCREENSHOT_DIR, f)
                    files.append((path, os.path.getmtime(path)))

            # Sort by modification time (oldest first)
            files.sort(key=lambda x: x[1])

            # Delete oldest files if we exceed limit
            while len(files) > MAX_SCREENSHOTS:
                oldest_file = files.pop(0)[0]
                try:
                    os.remove(oldest_file)
                except OSError:
                    pass
        except Exception:
            pass  # Don't let cleanup errors affect logging
