"""
Audit Logger Service
Session event logging, parity checking, and pre-flight validation for debugging.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from utils.debug import debug_log as _debug_log


class EventType(str, Enum):
    """Types of audit events."""
    SEGMENT_START = "segment_start"
    SEGMENT_END = "segment_end"
    STATE_CHANGE = "state_change"
    AUDIO_START = "audio_start"
    AUDIO_END = "audio_end"
    FORM_UPDATE = "form_update"
    PARITY_CHECK = "parity_check"
    INTERPOLATION_START = "interpolation_start"
    INTERPOLATION_END = "interpolation_end"
    ERROR = "error"
    VALIDATION_ERROR = "validation_error"


class ParityStatus(str, Enum):
    """Status of audio/visual parity check."""
    SYNCHRONIZED = "SYNCHRONIZED"
    AUDIO_BEHIND = "AUDIO_BEHIND"
    VISUAL_BEHIND = "VISUAL_BEHIND"
    DESYNC = "DESYNC"


@dataclass
class AuditEvent:
    """A single audit event."""
    ts: int  # Timestamp in ms since session start
    type: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "ts": self.ts,
            "type": self.type,
            **self.data
        }


@dataclass
class AuditSummary:
    """Summary statistics for the session."""
    parity_violations: int = 0
    avg_establishing_ms: float = 0.0
    total_form_time_ms: int = 0
    perfect_form_time_ms: int = 0
    good_form_time_ms: int = 0
    segments_completed: int = 0
    total_segments: int = 0
    errors: List[str] = field(default_factory=list)


class SessionAuditLogger:
    """Audit logger for a single yoga session."""

    def __init__(self, session_id: str, manifest: Optional[Dict] = None):
        self.session_id = session_id
        self.manifest = manifest
        self.events: List[AuditEvent] = []
        self.start_time_ms = int(time.time() * 1000)
        self.establishing_times: List[int] = []
        self.parity_violations = 0

    def _now_ms(self) -> int:
        """Get current timestamp in ms since session start."""
        return int(time.time() * 1000) - self.start_time_ms

    def log_segment_start(self, segment_index: int, pose_id: str, side: Optional[str] = None):
        """Log the start of a segment."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.SEGMENT_START,
            data={
                "segmentIndex": segment_index,
                "poseId": pose_id,
                "side": side
            }
        ))

    def log_segment_end(self, segment_index: int, pose_id: str, completed: bool = True):
        """Log the end of a segment."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.SEGMENT_END,
            data={
                "segmentIndex": segment_index,
                "poseId": pose_id,
                "completed": completed
            }
        ))

    def log_state_change(self, from_state: str, to_state: str, segment_index: Optional[int] = None):
        """Log a state machine transition."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.STATE_CHANGE,
            data={
                "from": from_state,
                "to": to_state,
                "segmentIndex": segment_index
            }
        ))

    def log_audio_start(self, audio_id: str, expected_duration_ms: int):
        """Log audio playback start."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.AUDIO_START,
            data={
                "audioId": audio_id,
                "expectedDurationMs": expected_duration_ms
            }
        ))

    def log_audio_end(self, audio_id: str, actual_duration_ms: Optional[int] = None):
        """Log audio playback end."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.AUDIO_END,
            data={
                "audioId": audio_id,
                "actualDurationMs": actual_duration_ms
            }
        ))

    def log_form_update(self, segment_index: int, match_score: float, form_level: str, timer_running: bool):
        """Log a form quality update."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.FORM_UPDATE,
            data={
                "segmentIndex": segment_index,
                "matchScore": match_score,
                "formLevel": form_level,
                "timerRunning": timer_running
            }
        ))

    def log_parity_check(
        self,
        audio_complete: bool,
        visual_ready: bool,
        interpolation_complete: bool
    ) -> ParityStatus:
        """
        Log a parity check between audio and visual states.

        Returns the parity status.
        """
        if audio_complete and visual_ready and interpolation_complete:
            status = ParityStatus.SYNCHRONIZED
        elif not audio_complete and visual_ready:
            status = ParityStatus.AUDIO_BEHIND
        elif audio_complete and not visual_ready:
            status = ParityStatus.VISUAL_BEHIND
        else:
            status = ParityStatus.DESYNC
            self.parity_violations += 1

        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.PARITY_CHECK,
            data={
                "audioComplete": audio_complete,
                "visualReady": visual_ready,
                "interpolationComplete": interpolation_complete,
                "status": status.value
            }
        ))

        return status

    def log_interpolation_start(self, from_index: int, to_index: int, duration_ms: int):
        """Log interpolation start."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.INTERPOLATION_START,
            data={
                "fromIndex": from_index,
                "toIndex": to_index,
                "durationMs": duration_ms
            }
        ))

    def log_interpolation_end(self, to_index: int):
        """Log interpolation completion."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.INTERPOLATION_END,
            data={
                "toIndex": to_index
            }
        ))

    def log_establishing_time(self, duration_ms: int):
        """Record time spent in ESTABLISHING state."""
        self.establishing_times.append(duration_ms)

    def log_error(self, error_type: str, message: str, details: Optional[Dict] = None):
        """Log an error event."""
        self.events.append(AuditEvent(
            ts=self._now_ms(),
            type=EventType.ERROR,
            data={
                "errorType": error_type,
                "message": message,
                "details": details or {}
            }
        ))

    def get_summary(self) -> AuditSummary:
        """Generate summary statistics."""
        # Calculate average establishing time
        avg_establishing = 0.0
        if self.establishing_times:
            avg_establishing = sum(self.establishing_times) / len(self.establishing_times)

        # Count segments
        segment_starts = [e for e in self.events if e.type == EventType.SEGMENT_START]
        segment_ends = [e for e in self.events if e.type == EventType.SEGMENT_END]

        # Collect errors
        errors = [
            e.data.get("message", "Unknown error")
            for e in self.events
            if e.type in (EventType.ERROR, EventType.VALIDATION_ERROR)
        ]

        return AuditSummary(
            parity_violations=self.parity_violations,
            avg_establishing_ms=avg_establishing,
            segments_completed=len(segment_ends),
            total_segments=len(segment_starts),
            errors=errors
        )

    def to_dict(self) -> Dict:
        """Export audit log as dictionary."""
        summary = self.get_summary()
        return {
            "sessionId": self.session_id,
            "generatedAt": datetime.now().isoformat(),
            "events": [e.to_dict() for e in self.events],
            "summary": {
                "parityViolations": summary.parity_violations,
                "avgEstablishingMs": round(summary.avg_establishing_ms, 2),
                "segmentsCompleted": summary.segments_completed,
                "totalSegments": summary.total_segments,
                "errors": summary.errors
            }
        }

    def save(self, output_dir: Optional[Path] = None):
        """Save audit log to file."""
        if output_dir is None:
            output_dir = Path("logs/yoga_audit")
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"audit_{self.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path = output_dir / filename

        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

        _debug_log(f"[AUDIT] Saved audit log to {output_path}")
        return output_path


class ManifestValidator:
    """Pre-flight validation for session manifests."""

    @staticmethod
    def validate(manifest: Dict) -> tuple[bool, List[str]]:
        """
        Validate a session manifest before session starts.

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Check version
        version = manifest.get("version")
        if version != "2.0":
            errors.append(f"Unsupported manifest version: {version}")

        # Check segments exist
        segments = manifest.get("segments", [])
        if not segments:
            errors.append("Manifest contains no segments")
            return False, errors

        # Validate each segment
        for i, segment in enumerate(segments):
            seg_errors = ManifestValidator._validate_segment(segment, i)
            errors.extend(seg_errors)

        # Check timing config
        timing = manifest.get("timing", {})
        if not timing:
            errors.append("Missing timing configuration")
        else:
            required_timing = ["instructionDurationMs", "transitionDurationMs", "establishingTimeoutMs"]
            for field in required_timing:
                if field not in timing:
                    errors.append(f"Missing timing field: {field}")

        # Check interpolation durations are reasonable
        for segment in segments:
            interp = segment.get("interpolation", {})
            duration = interp.get("durationMs", 0)
            if duration < 1000 or duration > 10000:
                errors.append(
                    f"Segment {segment.get('index')}: interpolation duration {duration}ms "
                    f"outside reasonable range (1000-10000ms)"
                )

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def _validate_segment(segment: Dict, index: int) -> List[str]:
        """Validate a single segment."""
        errors = []
        prefix = f"Segment {index}"

        # Required fields
        required = ["index", "type", "poseId", "holdDurationMs"]
        for field in required:
            if field not in segment:
                errors.append(f"{prefix}: missing required field '{field}'")

        # Check landmarks
        landmarks = segment.get("landmarks", {})
        active_landmarks = landmarks.get("active", [])
        if not active_landmarks:
            errors.append(f"{prefix}: missing active landmarks")
        elif len(active_landmarks) != 33:
            errors.append(f"{prefix}: expected 33 landmarks, got {len(active_landmarks)}")

        # Check angles
        angles = segment.get("angles", {})
        active_angles = angles.get("active", {})
        if not active_angles:
            errors.append(f"{prefix}: missing active angles")

        # Check hold duration
        hold_duration = segment.get("holdDurationMs", 0)
        if hold_duration < 5000:
            errors.append(f"{prefix}: hold duration {hold_duration}ms is too short (min 5000ms)")
        elif hold_duration > 300000:
            errors.append(f"{prefix}: hold duration {hold_duration}ms is too long (max 300000ms)")

        return errors


# Factory function for creating audit loggers
def create_audit_logger(session_id: str, manifest: Optional[Dict] = None) -> SessionAuditLogger:
    """Create a new audit logger for a session."""
    return SessionAuditLogger(session_id, manifest)


# Singleton validator
manifest_validator = ManifestValidator()
