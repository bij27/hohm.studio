from enum import Enum
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

class PostureStatus(str, Enum):
    GOOD = "good"
    WARNING = "warning"
    BAD = "bad"

class PostureIssueType(str, Enum):
    FORWARD_HEAD = "forward_head"
    UNEVEN_SHOULDERS = "uneven_shoulders"
    SLOUCHING = "slouching"
    NECK_TILT = "neck_tilt"
    SCREEN_DISTANCE = "screen_distance"

class PostureIssue(BaseModel):
    type: PostureIssueType
    severity: str  # "mild", "moderate", "severe"
    measurement: str
    advice: str

class CalibrationProfile(BaseModel):
    created_at: datetime
    ideal_ear_shoulder_angle: float
    ideal_shoulder_hip_angle: float
    baseline_shoulder_height: float
    baseline_head_distance: float
    baseline_body_size: float # Added to track screen distance

class PostureMetrics(BaseModel):
    forward_head_distance: float
    shoulder_asymmetry: float
    slouch_angle: float
    neck_tilt_angle: float
    screen_distance_change: float

class LogEntry(BaseModel):
    timestamp: datetime
    status: PostureStatus
    score: float
    issues: List[PostureIssue]
    metrics: PostureMetrics

class SessionSummary(BaseModel):
    session_id: str
    start_time: datetime
    end_time: datetime
    duration_minutes: float
    good_posture_percentage: float
    average_score: float
    total_logs: int
    most_common_issues: List[PostureIssueType]
