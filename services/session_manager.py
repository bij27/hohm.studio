import uuid
from datetime import datetime
from typing import Dict, List, Optional
from models.schemas import PostureStatus, PostureIssue

class SessionManager:
    """
    Manages the lifecycle of a single posture monitoring session.
    Tracks good and bad posture time separately for accurate grading.
    """
    # Maximum delta to prevent timer overflow (0.5 seconds max between updates)
    MAX_DELTA_SEC = 0.5

    def __init__(self):
        self.session_id: Optional[str] = None
        self.start_time: Optional[datetime] = None
        self.good_time_sec: float = 0
        self.bad_time_sec: float = 0
        self.total_score: float = 0
        self.log_count: int = 0
        self.is_active: bool = False
        self.last_update_time: Optional[datetime] = None

    def start(self):
        self.session_id = str(uuid.uuid4())
        self.start_time = datetime.now()
        self.last_update_time = self.start_time
        self.good_time_sec = 0
        self.bad_time_sec = 0
        self.total_score = 0
        self.log_count = 0
        self.is_active = True
        return self.session_id

    def update_stats(self, status: PostureStatus, score: float):
        """Track score for averaging. Timing is handled by frontend."""
        if not self.is_active:
            return

        self.total_score += score
        self.log_count += 1

    def stop(self):
        self.is_active = False

        total_tracked = self.good_time_sec + self.bad_time_sec
        duration_sec = (datetime.now() - self.start_time).total_seconds()

        # Calculate good posture percentage based on tracked time
        good_percentage = (self.good_time_sec / total_tracked * 100) if total_tracked > 0 else 100

        # Calculate grade: weighted by good posture percentage and average score
        avg_score = self.total_score / self.log_count if self.log_count > 0 else 10
        # Grade = 60% based on good posture %, 40% based on average score
        grade = (good_percentage / 100 * 10) * 0.6 + avg_score * 0.4

        return {
            "session_id": self.session_id,
            "duration_minutes": duration_sec / 60.0,
            "good_time_minutes": self.good_time_sec / 60.0,
            "bad_time_minutes": self.bad_time_sec / 60.0,
            "average_score": round(grade, 1),  # This is now the calculated grade
            "good_posture_percentage": round(good_percentage, 1)
        }
