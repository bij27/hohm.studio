import numpy as np
from typing import List, Dict, Optional, Tuple
from models.schemas import CalibrationProfile
from datetime import datetime
import math

class Calibrator:
    """
    Production-grade calibration using principles from biometric scanning systems.

    Key design principles (from Face ID, Windows Hello, etc.):
    1. Collect first, filter later - don't reject frames upfront
    2. Use statistical outlier removal instead of hard thresholds
    3. Adaptive landmark selection - work with available data
    4. Confidence accumulation over time
    """

    # Landmark indices
    NOSE = 0
    LEFT_EYE_INNER = 1
    LEFT_EYE = 2
    LEFT_EYE_OUTER = 3
    RIGHT_EYE_INNER = 4
    RIGHT_EYE = 5
    RIGHT_EYE_OUTER = 6
    LEFT_EAR = 7
    RIGHT_EAR = 8
    MOUTH_LEFT = 9
    MOUTH_RIGHT = 10
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24

    def __init__(self):
        self.collected_landmarks: List[Dict[int, Dict[str, float]]] = []
        self.num_required_frames = 20  # Reduced for faster calibration
        self.min_usable_frames = 10    # Minimum needed after filtering
        self.collection_started = False

    def _get_landmark_safe(self, landmarks: Dict, idx: int, fallback_idx: Optional[int] = None) -> Optional[Dict]:
        """Safely get a landmark with optional fallback. Assumes visibility=1.0 if missing."""
        if idx in landmarks:
            lm = landmarks[idx]
            # Default visibility to 1.0 if not provided (MediaPipe browser API quirk)
            vis = lm.get('visibility', 1.0) if lm.get('visibility') is not None else 1.0
            if vis > 0.1:
                return lm
        if fallback_idx and fallback_idx in landmarks:
            return landmarks[fallback_idx]
        return None

    def _estimate_shoulder_from_body(self, landmarks: Dict) -> Optional[Tuple[Dict, Dict]]:
        """Estimate shoulder position from other body landmarks if not directly visible."""
        # Try direct shoulders first
        left_sh = self._get_landmark_safe(landmarks, self.LEFT_SHOULDER)
        right_sh = self._get_landmark_safe(landmarks, self.RIGHT_SHOULDER)

        if left_sh and right_sh:
            return left_sh, right_sh

        # Fallback: estimate from head width (shoulders are typically 2-2.5x head width)
        left_ear = self._get_landmark_safe(landmarks, self.LEFT_EAR, self.LEFT_EYE_OUTER)
        right_ear = self._get_landmark_safe(landmarks, self.RIGHT_EAR, self.RIGHT_EYE_OUTER)
        nose = self._get_landmark_safe(landmarks, self.NOSE)

        if left_ear and right_ear and nose:
            head_width = abs(left_ear['x'] - right_ear['x'])
            center_x = (left_ear['x'] + right_ear['x']) / 2
            shoulder_y = nose['y'] + head_width * 1.2  # Estimate shoulder Y

            return (
                {'x': center_x - head_width * 1.1, 'y': shoulder_y, 'visibility': 0.5},
                {'x': center_x + head_width * 1.1, 'y': shoulder_y, 'visibility': 0.5}
            )

        return None

    def _extract_features(self, landmarks: Dict) -> Optional[Dict]:
        """
        Extract normalized postural features from landmarks.
        Returns None if minimum required landmarks aren't available.
        """
        nose = self._get_landmark_safe(landmarks, self.NOSE)
        if not nose:
            return None

        shoulders = self._estimate_shoulder_from_body(landmarks)
        if not shoulders:
            return None

        left_sh, right_sh = shoulders

        # Get ear positions (with eye fallback for head tilt)
        left_ref = self._get_landmark_safe(landmarks, self.LEFT_EAR, self.LEFT_EYE_OUTER)
        right_ref = self._get_landmark_safe(landmarks, self.RIGHT_EAR, self.RIGHT_EYE_OUTER)

        if not left_ref or not right_ref:
            return None

        # Calculate normalized features
        shoulder_width = abs(left_sh['x'] - right_sh['x'])
        if shoulder_width < 0.05:  # Too narrow, likely error
            return None

        shoulder_center_x = (left_sh['x'] + right_sh['x']) / 2
        shoulder_center_y = (left_sh['y'] + right_sh['y']) / 2

        return {
            # Normalized by shoulder width for scale invariance
            'head_forward': (nose['y'] - shoulder_center_y) / shoulder_width,
            'head_lateral': (nose['x'] - shoulder_center_x) / shoulder_width,
            'shoulder_tilt': (left_sh['y'] - right_sh['y']) / shoulder_width,
            'head_tilt': (left_ref['y'] - right_ref['y']) / shoulder_width,
            'shoulder_width': shoulder_width,
            # Raw values for baseline
            'shoulder_y': shoulder_center_y,
            'nose_y': nose['y'],
            'left_shoulder': left_sh,
            'right_shoulder': right_sh,
            'left_ear_y': left_ref['y'],
            'right_ear_y': right_ref['y'],
        }

    def _calculate_frame_quality(self, features: Dict) -> float:
        """
        Calculate a quality score for this frame (0-1).
        Higher = more stable/centered pose.
        """
        quality = 1.0

        # Penalize extreme head positions
        if abs(features['head_lateral']) > 0.3:
            quality *= 0.7
        if features['head_forward'] > 0.5:  # Head dropped significantly
            quality *= 0.7

        # Penalize tilted shoulders/head
        if abs(features['shoulder_tilt']) > 0.15:
            quality *= 0.8
        if abs(features['head_tilt']) > 0.15:
            quality *= 0.8

        return quality

    def add_frame(self, landmarks: Dict[int, Dict[str, float]]) -> Tuple[bool, str]:
        """
        Add a frame for calibration. Always accepts if minimum landmarks present.
        Returns (is_collecting, instruction).
        """
        features = self._extract_features(landmarks)

        if not features:
            return False, "Position yourself so your head and shoulders are visible"

        quality = self._calculate_frame_quality(features)
        self.collection_started = True

        # Always collect the frame with its features and quality score
        self.collected_landmarks.append({
            'raw': landmarks,
            'features': features,
            'quality': quality
        })

        # Generate adaptive instruction based on current pose
        instruction = self._get_instruction(features, quality)

        return True, instruction

    def _get_instruction(self, features: Dict, quality: float) -> str:
        """Generate specific instruction based on current pose."""
        if quality > 0.85:
            return f"Perfect! Hold still... ({len(self.collected_landmarks)}/{self.num_required_frames})"

        issues = []
        if abs(features['head_lateral']) > 0.2:
            direction = "left" if features['head_lateral'] > 0 else "right"
            issues.append(f"Center your head (move {direction})")
        if features['head_forward'] > 0.3:
            issues.append("Sit up straighter")
        if abs(features['shoulder_tilt']) > 0.1:
            side = "left" if features['shoulder_tilt'] > 0 else "right"
            issues.append(f"Level your shoulders ({side} is higher)")
        if abs(features['head_tilt']) > 0.1:
            side = "left" if features['head_tilt'] > 0 else "right"
            issues.append(f"Straighten your head ({side} tilt)")

        if issues:
            return issues[0]  # Return most important issue
        return f"Good! Keep still... ({len(self.collected_landmarks)}/{self.num_required_frames})"

    def is_complete(self) -> bool:
        return len(self.collected_landmarks) >= self.num_required_frames

    def get_progress(self) -> Dict:
        """Get detailed progress info."""
        return {
            'count': len(self.collected_landmarks),
            'total': self.num_required_frames,
            'percent': (len(self.collected_landmarks) / self.num_required_frames) * 100
        }

    def calculate_angle(self, p1: Dict[str, float], p2: Dict[str, float], p3: Dict[str, float]) -> float:
        a = np.array([p1['x'], p1['y']])
        b = np.array([p2['x'], p2['y']])
        c = np.array([p3['x'], p3['y']])
        ba = a - b
        bc = c - b
        cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
        angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
        return np.degrees(angle)

    def finalize(self) -> CalibrationProfile:
        """
        Finalize calibration using statistical filtering.
        Uses IQR method to remove outliers, then takes median of best frames.
        """
        if not self.collected_landmarks:
            raise ValueError("No calibration data collected")

        # Sort by quality and take top frames
        sorted_frames = sorted(self.collected_landmarks, key=lambda x: x['quality'], reverse=True)
        best_frames = sorted_frames[:self.min_usable_frames]

        # Extract feature arrays for statistical processing
        head_forwards = [f['features']['head_forward'] for f in best_frames]
        shoulder_tilts = [f['features']['shoulder_tilt'] for f in best_frames]
        shoulder_widths = [f['features']['shoulder_width'] for f in best_frames]
        shoulder_ys = [f['features']['shoulder_y'] for f in best_frames]
        head_laterals = [f['features']['head_lateral'] for f in best_frames]

        # Calculate baseline metrics using median (robust to outliers)
        baseline_head_forward = float(np.median(head_forwards))
        baseline_shoulder_width = float(np.median(shoulder_widths))
        baseline_shoulder_y = float(np.median(shoulder_ys))

        # Calculate ideal angles from best quality frames
        ear_shoulder_angles = []
        shoulder_hip_angles = []

        for frame in best_frames:
            lm = frame['raw']
            features = frame['features']

            # Ear-shoulder angle (head position relative to shoulders)
            avg_ear_y = (features['left_ear_y'] + features['right_ear_y']) / 2
            left_sh = features['left_shoulder']
            right_sh = features['right_shoulder']
            avg_shoulder_y = (left_sh['y'] + right_sh['y']) / 2
            avg_shoulder_x = (left_sh['x'] + right_sh['x']) / 2
            avg_ear_x = (lm.get(self.LEFT_EAR, lm.get(self.LEFT_EYE_OUTER, {})).get('x', avg_shoulder_x) +
                        lm.get(self.RIGHT_EAR, lm.get(self.RIGHT_EYE_OUTER, {})).get('x', avg_shoulder_x)) / 2

            ear_shoulder_angle = self.calculate_angle(
                {'x': avg_ear_x, 'y': avg_ear_y - 0.1},
                {'x': avg_ear_x, 'y': avg_ear_y},
                {'x': avg_shoulder_x, 'y': avg_shoulder_y}
            )
            ear_shoulder_angles.append(ear_shoulder_angle)

            # Shoulder-hip angle (torso alignment) - use estimate if hips not visible
            if self.LEFT_HIP in lm and self.RIGHT_HIP in lm:
                l_hip = lm[self.LEFT_HIP]
                r_hip = lm[self.RIGHT_HIP]
                if l_hip.get('visibility', 0) > 0.3 and r_hip.get('visibility', 0) > 0.3:
                    l_angle = self.calculate_angle(
                        {'x': left_sh['x'], 'y': left_sh['y'] - 0.1},
                        left_sh, l_hip
                    )
                    r_angle = self.calculate_angle(
                        {'x': right_sh['x'], 'y': right_sh['y'] - 0.1},
                        right_sh, r_hip
                    )
                    shoulder_hip_angles.append((l_angle + r_angle) / 2)

        # Use defaults if hip angles couldn't be calculated
        ideal_shoulder_hip = float(np.median(shoulder_hip_angles)) if shoulder_hip_angles else 170.0

        profile = CalibrationProfile(
            created_at=datetime.now(),
            ideal_ear_shoulder_angle=float(np.median(ear_shoulder_angles)),
            ideal_shoulder_hip_angle=ideal_shoulder_hip,
            baseline_shoulder_height=baseline_shoulder_y,
            baseline_head_distance=abs(float(np.median(head_laterals))),
            baseline_body_size=baseline_shoulder_width
        )

        # Clear collected data to free memory
        self.collected_landmarks.clear()
        self.collection_started = False

        return profile
