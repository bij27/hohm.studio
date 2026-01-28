import numpy as np
import math
import time
from collections import deque
from typing import Dict, List, Optional, Tuple
from models.schemas import PostureMetrics, PostureIssue, PostureIssueType, PostureStatus, CalibrationProfile
import config as cfg


class PostureAnalyzer:
    """
    Production-grade posture analyzer with temporal smoothing and adaptive thresholds.

    Key techniques used by professional biometric/health apps:
    1. Exponential moving average (EMA) for score smoothing
    2. Dead zones to ignore micro-movements
    3. Graduated penalty curves (not harsh thresholds)
    4. Hysteresis for status changes
    5. Weighted average scoring (not min-based)
    """

    # Smoothing parameters
    SCORE_HISTORY_SIZE = 10  # ~2 seconds at 5fps
    EMA_ALPHA = 0.5  # Higher = more responsive, lower = smoother (0.5 = balanced)

    # Dead zone tolerances (tight for responsive detection)
    DEAD_ZONE_SHOULDER_ASYM = 0.008  # 0.8% shoulder height difference
    DEAD_ZONE_NECK_TILT = 0.005      # Very small head tilts
    DEAD_ZONE_HEAD_DROP = 0.01       # 1% vertical movement tolerance
    DEAD_ZONE_DISTANCE = 3.0         # 3% distance change

    # Score weights (not all metrics equally important)
    WEIGHT_SLOUCH = 0.35
    WEIGHT_HEAD_DROP = 0.25
    WEIGHT_SHOULDER_ASYM = 0.15
    WEIGHT_NECK_TILT = 0.15
    WEIGHT_DISTANCE = 0.10

    def __init__(self, profile: Optional[CalibrationProfile] = None):
        self.profile = profile
        self.bad_posture_start_time: Optional[float] = None
        self.alert_triggered = False

        # Temporal smoothing buffers
        self.score_history = deque(maxlen=self.SCORE_HISTORY_SIZE)
        self.smoothed_score = 10.0
        self.last_status = "good"
        self.status_hold_counter = 0  # Hysteresis counter

    def calculate_angle(self, p1: Dict[str, float], p2: Dict[str, float], p3: Dict[str, float]) -> float:
        """Calculates the angle at p2 between p1 and p3."""
        a = np.array([p1['x'], p1['y']])
        b = np.array([p2['x'], p2['y']])
        c = np.array([p3['x'], p3['y']])

        ba = a - b
        bc = c - b

        denom = np.linalg.norm(ba) * np.linalg.norm(bc)
        if denom < 1e-6:
            return 0.0
        cosine_angle = np.dot(ba, bc) / denom
        angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))

        return np.degrees(angle)

    def _apply_dead_zone(self, value: float, dead_zone: float) -> float:
        """Apply dead zone - values within dead zone become 0."""
        if abs(value) <= dead_zone:
            return 0.0
        # Subtract dead zone from the value (so penalty starts from 0 after dead zone)
        return abs(value) - dead_zone

    def _graduated_penalty(self, deviation: float, mild_threshold: float, severe_threshold: float) -> float:
        """
        Calculate a graduated score (10 to 1) based on deviation.
        More aggressive scoring for clearer feedback.

        - Below mild_threshold: score 10-8 (good)
        - At severe_threshold: score ~4
        - Beyond severe: drops to 1 quickly
        """
        if deviation <= 0:
            return 10.0
        if deviation <= mild_threshold:
            # Quick reduction: 10 -> 8 in the mild zone
            return 10.0 - (deviation / mild_threshold) * 2.0
        elif deviation <= severe_threshold:
            # Aggressive reduction: 8 -> 4 in the moderate zone
            progress = (deviation - mild_threshold) / (severe_threshold - mild_threshold)
            return 8.0 - progress * 4.0
        else:
            # Beyond severe: 4 -> 1 quickly
            excess = deviation - severe_threshold
            return max(1.0, 4.0 - excess * 1.5)

    def analyze(self, landmarks: Dict[int, Dict[str, float]]) -> Tuple[PostureMetrics, float, List[PostureIssue]]:
        """
        Main analysis function with temporal smoothing.
        """
        try:
            # Extract raw metrics
            shoulder_y = (landmarks[11]['y'] + landmarks[12]['y']) / 2
            head_drop = landmarks[0]['y'] - shoulder_y  # Positive = head dropped

            shoulder_asym = abs(landmarks[11]['y'] - landmarks[12]['y'])

            # Slouching calculation
            slouch_deviation = 0.0
            if 23 in landmarks and 24 in landmarks:
                vis_l = landmarks[23].get('visibility') or 1.0
                vis_r = landmarks[24].get('visibility') or 1.0
                if vis_l > 0.3 and vis_r > 0.3:
                    l_angle = self.calculate_angle(
                        {'x': landmarks[11]['x'], 'y': landmarks[11]['y'] - 0.1},
                        landmarks[11], landmarks[23]
                    )
                    r_angle = self.calculate_angle(
                        {'x': landmarks[12]['x'], 'y': landmarks[12]['y'] - 0.1},
                        landmarks[12], landmarks[24]
                    )
                    avg_slouch_angle = (l_angle + r_angle) / 2
                    if self.profile:
                        slouch_deviation = abs(avg_slouch_angle - self.profile.ideal_shoulder_hip_angle)

            if slouch_deviation == 0 and self.profile:
                # Fallback: use shoulder height change as slouch indicator
                slouch_deviation = abs(shoulder_y - self.profile.baseline_shoulder_height) * 50

            # Neck tilt
            neck_tilt = abs(landmarks[7]['y'] - landmarks[8]['y'])

            # Screen distance
            shoulder_width = abs(landmarks[11]['x'] - landmarks[12]['x'])
            dist_change_pct = 0.0
            if self.profile and self.profile.baseline_body_size > 0:
                dist_change_pct = abs(shoulder_width - self.profile.baseline_body_size) / self.profile.baseline_body_size * 100

            metrics = PostureMetrics(
                forward_head_distance=head_drop,
                shoulder_asymmetry=shoulder_asym,
                slouch_angle=slouch_deviation,
                neck_tilt_angle=neck_tilt * 100,
                screen_distance_change=dist_change_pct
            )

            # Calculate raw score
            raw_score, issues = self._calculate_score_and_issues(metrics, landmarks)

            # Apply temporal smoothing (EMA)
            self.score_history.append(raw_score)
            if len(self.score_history) >= 3:
                # Use EMA for smoothing
                self.smoothed_score = (self.EMA_ALPHA * raw_score +
                                       (1 - self.EMA_ALPHA) * self.smoothed_score)
            else:
                self.smoothed_score = raw_score

            # Round to 1 decimal for display
            final_score = round(self.smoothed_score, 1)

            return metrics, final_score, issues

        except Exception:
            # Return safe defaults on error
            return PostureMetrics(
                forward_head_distance=0, shoulder_asymmetry=0,
                slouch_angle=0, neck_tilt_angle=0, screen_distance_change=0
            ), self.smoothed_score, []

    def _calculate_score_and_issues(self, metrics: PostureMetrics, landmarks: Dict) -> Tuple[float, List[PostureIssue]]:
        """Calculate score using graduated penalties and weighted average."""
        if not self.profile:
            return 10.0, []

        issues = []
        weighted_scores = []

        # 1. Shoulder Asymmetry (with dead zone) - TIGHTER thresholds
        asym_adjusted = self._apply_dead_zone(metrics.shoulder_asymmetry, self.DEAD_ZONE_SHOULDER_ASYM)
        asym_score = self._graduated_penalty(asym_adjusted, 0.01, 0.03)  # 1-3% range (tighter)
        weighted_scores.append((asym_score, self.WEIGHT_SHOULDER_ASYM))

        if asym_score < 9.0:
            severity = "mild" if asym_score >= 7 else "moderate" if asym_score >= 5 else "severe"
            issues.append(PostureIssue(
                type=PostureIssueType.UNEVEN_SHOULDERS,
                severity=severity,
                measurement=f"{metrics.shoulder_asymmetry*100:.1f}%",
                advice="Level your shoulders - one is higher than the other"
            ))

        # 2. Slouching (main posture indicator) - TIGHTER thresholds
        slouch_score = self._graduated_penalty(metrics.slouch_angle, 3.0, 8.0)  # 3-8 degree range (tighter)
        weighted_scores.append((slouch_score, self.WEIGHT_SLOUCH))

        if slouch_score < 9.0:
            severity = "mild" if slouch_score >= 7 else "moderate" if slouch_score >= 5 else "severe"
            issues.append(PostureIssue(
                type=PostureIssueType.SLOUCHING,
                severity=severity,
                measurement=f"{metrics.slouch_angle:.1f}°",
                advice="Sit up straight - you're slouching forward"
            ))

        # 3. Neck Tilt (with dead zone) - TIGHTER thresholds
        tilt_adjusted = self._apply_dead_zone(metrics.neck_tilt_angle / 100, self.DEAD_ZONE_NECK_TILT)
        tilt_score = self._graduated_penalty(tilt_adjusted, 0.01, 0.03)  # 1-3% range (tighter)
        weighted_scores.append((tilt_score, self.WEIGHT_NECK_TILT))

        if tilt_score < 9.0:
            severity = "mild" if tilt_score >= 7 else "moderate" if tilt_score >= 5 else "severe"
            issues.append(PostureIssue(
                type=PostureIssueType.NECK_TILT,
                severity=severity,
                measurement=f"{metrics.neck_tilt_angle:.1f}",
                advice="Keep your head level - it's tilting to one side"
            ))

        # 4. Forward Head / Head Drop (with dead zone) - TIGHTER thresholds
        head_drop_adjusted = self._apply_dead_zone(metrics.forward_head_distance, self.DEAD_ZONE_HEAD_DROP)
        head_score = self._graduated_penalty(head_drop_adjusted, 0.02, 0.05)  # 2-5% range (tighter)
        weighted_scores.append((head_score, self.WEIGHT_HEAD_DROP))

        if head_score < 9.0:
            severity = "mild" if head_score >= 7 else "moderate" if head_score >= 5 else "severe"
            issues.append(PostureIssue(
                type=PostureIssueType.FORWARD_HEAD,
                severity=severity,
                measurement=f"{metrics.forward_head_distance*100:.1f}%",
                advice="Pull your head back - chin tuck position"
            ))

        # 5. Screen Distance (with dead zone) - TIGHTER thresholds
        dist_adjusted = self._apply_dead_zone(metrics.screen_distance_change, self.DEAD_ZONE_DISTANCE)
        dist_score = self._graduated_penalty(dist_adjusted, 3.0, 10.0)  # 3-10% range (tighter)
        weighted_scores.append((dist_score, self.WEIGHT_DISTANCE))

        if dist_score < 9.0:
            issues.append(PostureIssue(
                type=PostureIssueType.SCREEN_DISTANCE,
                severity="mild" if dist_score >= 7 else "moderate",
                measurement=f"{metrics.screen_distance_change:.1f}%",
                advice="Move back from your screen"
            ))

        # Calculate weighted average (much fairer than min-based)
        total_weight = sum(w for _, w in weighted_scores)
        final_score = sum(s * w for s, w in weighted_scores) / total_weight if total_weight > 0 else 10.0

        # Only report top 2 most significant issues
        issues.sort(key=lambda x: {"severe": 0, "moderate": 1, "mild": 2}.get(x.severity, 3))
        issues = issues[:2]

        return final_score, issues

    def check_alert_condition(self, score: float) -> Tuple[bool, bool]:
        """
        Returns (should_alert, play_sound).
        Uses hysteresis - must stay bad for sustained period.
        """
        current_time = time.time()

        # Use smoothed score for alert decisions
        if self.smoothed_score < 7.0:  # Lowered threshold from 8.0
            if self.bad_posture_start_time is None:
                self.bad_posture_start_time = current_time
                return False, False

            elapsed = current_time - self.bad_posture_start_time
            # Require longer sustained bad posture before alerting
            if elapsed >= cfg.CONSECUTIVE_BAD_POSTURE_SECONDS + 2:  # Add 2 second buffer
                if not self.alert_triggered:
                    self.alert_triggered = True
                    return True, True
                # Repeat alert every 30 seconds if still bad
                return elapsed % 30 < 1, False
        else:
            # Hysteresis: require good posture for a bit before clearing
            if self.bad_posture_start_time is not None:
                if self.smoothed_score >= 8.0:  # Need to be solidly good
                    self.bad_posture_start_time = None
                    self.alert_triggered = False

        return False, False

    def get_status_with_hysteresis(self, score: float) -> str:
        """
        Get status with hysteresis to prevent rapid flickering.
        Status only changes after sustained deviation.
        """
        # Determine raw status - adjusted thresholds for stricter scoring
        if score >= 7.0:
            new_status = "good"
        elif score >= 5.0:
            new_status = "warning"
        else:
            new_status = "bad"

        # Apply light hysteresis (faster response)
        if new_status != self.last_status:
            self.status_hold_counter += 1
            # Only need 2 consecutive readings for faster response
            if self.status_hold_counter >= 2:
                self.last_status = new_status
                self.status_hold_counter = 0
        else:
            self.status_hold_counter = 0

        return self.last_status
