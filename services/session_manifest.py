"""
Session Manifest Generator
Generates v2.0 session manifests with segments, interpolation keyframes, bilateral sets, and audio refs.
"""

import uuid
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from copy import deepcopy

from services.pose_graph import pose_graph
from services.pose_mirroring import generate_bilateral_pair, get_side_landmarks, get_side_angles
from utils.debug import debug_log as _debug_log


# Session style configurations
SESSION_STYLES = {
    "power": {
        "name": "Power Flow",
        "description": "Efficient workout with quick transitions",
        "instructionDurationMs": 4000,      # Shorter instructions
        "transitionDurationMs": 2000,       # Quick transitions
        "establishingTimeoutMs": 6000,      # Less settling time
        "formMatchThreshold": 0.40,         # Slightly more lenient
        "holdMultiplier": 0.8,              # Shorter holds
        "breathCues": False
    },
    "vinyasa": {
        "name": "Mindful Vinyasa",
        "description": "Breath-centered meditative practice",
        "instructionDurationMs": 6000,      # Time to breathe and listen
        "transitionDurationMs": 4000,       # Breath-paced transitions
        "establishingTimeoutMs": 12000,     # More settling time
        "formMatchThreshold": 0.45,         # Standard threshold
        "holdMultiplier": 1.2,              # Longer holds
        "breathCues": True
    }
}


def get_trait_timing_modifier(pose: Dict, session_style: str) -> Dict[str, float]:
    """
    Calculate timing modifiers based on pose traits and session style.

    Returns multipliers for hold duration and transition duration.
    """
    traits = pose.get("traits", {})
    intensity = traits.get("intensity", "medium")
    stillness = traits.get("stillness", "medium")
    breath_focus = traits.get("breathFocus", "medium")

    # Convert trait levels to numeric values
    level_map = {"low": 0.0, "medium": 0.5, "high": 1.0}
    intensity_val = level_map.get(intensity, 0.5)
    stillness_val = level_map.get(stillness, 0.5)
    breath_val = level_map.get(breath_focus, 0.5)

    if session_style == "power":
        # Power flow: high intensity = shorter holds, low stillness = even shorter
        hold_mod = 1.0 - (intensity_val * 0.15) - ((1 - stillness_val) * 0.1)
        trans_mod = 0.9  # Always quick transitions
    else:  # vinyasa
        # Vinyasa: high breath focus = longer holds, high stillness = even longer
        hold_mod = 1.0 + (breath_val * 0.2) + (stillness_val * 0.15)
        # High intensity poses get slightly shorter even in vinyasa
        hold_mod -= (intensity_val * 0.1)
        trans_mod = 1.0 + (breath_val * 0.2)  # Breath-focused = slower transitions

    # Clamp to reasonable range
    hold_mod = max(0.7, min(1.5, hold_mod))
    trans_mod = max(0.8, min(1.4, trans_mod))

    return {
        "hold": hold_mod,
        "transition": trans_mod
    }


@dataclass
class InterpolationData:
    """Interpolation keyframes between poses."""
    from_index: Optional[int]
    duration_ms: int
    easing: str = "easeInOut"


@dataclass
class AudioRef:
    """Reference to an audio cue."""
    timing: str  # "pose_start", "pose_holding", "pose_midpoint", "pose_end"
    audio_id: str


@dataclass
class LandmarksData:
    """Landmarks for active and mirrored pose."""
    active: List[Dict]
    mirrored: List[Dict]


@dataclass
class AnglesData:
    """Angles for active and mirrored pose."""
    active: Dict[str, float]
    mirrored: Dict[str, float]


@dataclass
class Segment:
    """A single segment in the session (pose or transition)."""
    index: int
    type: str  # "pose" or "bridge"
    pose_id: str
    side: Optional[str]  # "left", "right", or None for symmetric poses
    set_id: Optional[str]
    hold_duration_ms: int
    is_bridge: bool

    landmarks: Dict  # {"active": [...], "mirrored": [...]}
    angles: Dict  # {"active": {...}, "mirrored": {...}}

    interpolation: Dict  # InterpolationData as dict
    audio_refs: List[Dict]  # List of AudioRef as dicts

    # Additional pose metadata
    name: str = ""
    sanskrit: str = ""
    instructions: List[str] = field(default_factory=list)
    image: str = ""


@dataclass
class SetInfo:
    """Information about a bilateral set."""
    name: str
    side: str
    segments: List[int]


@dataclass
class TimingConfig:
    """Timing configuration for the session."""
    instruction_duration_ms: int = 8000
    transition_duration_ms: int = 3000
    establishing_timeout_ms: int = 10000
    form_match_threshold: float = 0.45


@dataclass
class SessionManifest:
    """Complete session manifest."""
    version: str = "2.0"
    session_id: str = ""
    total_duration_ms: int = 0

    timing: Dict = field(default_factory=dict)
    segments: List[Dict] = field(default_factory=list)
    audio: Dict = field(default_factory=dict)
    sets: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": self.version,
            "sessionId": self.session_id,
            "totalDurationMs": self.total_duration_ms,
            "timing": self.timing,
            "segments": self.segments,
            "audio": self.audio,
            "sets": self.sets
        }


class SessionManifestGenerator:
    """Generates session manifests with bridge injection and bilateral symmetry."""

    def __init__(self, poses_path: Optional[Path] = None):
        """Initialize with pose data."""
        if poses_path is None:
            poses_path = Path("static/data/yoga/poses.json")

        self.poses: Dict[str, Dict] = {}
        self._load_poses(poses_path)

    def _load_poses(self, path: Path):
        """Load pose data from JSON file."""
        try:
            with open(path) as f:
                data = json.load(f)
                for pose in data.get("poses", []):
                    self.poses[pose["id"]] = pose
            _debug_log(f"[MANIFEST] Loaded {len(self.poses)} poses")
        except Exception as e:
            _debug_log(f"[MANIFEST] Error loading poses: {e}")

    def get_pose(self, pose_id: str) -> Optional[Dict]:
        """Get pose data by ID."""
        return self.poses.get(pose_id)

    def generate(
        self,
        duration_mins: int,
        focus: str = "all",
        difficulty: str = "beginner",
        pose_ids: Optional[List[str]] = None,
        session_style: str = "vinyasa"
    ) -> SessionManifest:
        """
        Generate a complete session manifest.

        Args:
            duration_mins: Target session duration in minutes
            focus: Focus area ("all", "balance", "flexibility", "strength", "relaxation")
            difficulty: Difficulty level ("beginner", "intermediate", "advanced")
            pose_ids: Optional explicit list of pose IDs (overrides auto-generation)
            session_style: "power" for efficient workout, "vinyasa" for breath-centered practice

        Returns:
            SessionManifest with all segments, timing, and audio refs
        """
        session_id = str(uuid.uuid4())

        # Get style config (default to vinyasa if invalid)
        style_config = SESSION_STYLES.get(session_style, SESSION_STYLES["vinyasa"])
        _debug_log(f"[MANIFEST] Session style: {style_config['name']}")

        # Build pose sequence
        if pose_ids:
            raw_sequence = pose_ids
        else:
            raw_sequence = self._build_auto_sequence(duration_mins, focus, difficulty)

        # Inject bridge poses
        optimized_sequence = pose_graph.optimize_sequence(raw_sequence)

        _debug_log(f"[MANIFEST] Raw sequence: {len(raw_sequence)} poses")
        _debug_log(f"[MANIFEST] Optimized sequence: {len(optimized_sequence)} poses")

        # Build segments with bilateral handling and style-based timing
        segments, sets = self._build_segments(optimized_sequence, session_style)

        # Calculate total duration
        total_duration_ms = sum(seg["holdDurationMs"] for seg in segments)
        total_duration_ms += pose_graph.calculate_total_transition_time(
            [seg["poseId"] for seg in segments]
        )

        # Build timing config from style
        timing = {
            "instructionDurationMs": style_config["instructionDurationMs"],
            "transitionDurationMs": style_config["transitionDurationMs"],
            "establishingTimeoutMs": style_config["establishingTimeoutMs"],
            "formMatchThreshold": style_config["formMatchThreshold"],
            "breathCues": style_config["breathCues"],
            "sessionStyle": session_style
        }

        manifest = SessionManifest(
            version="2.0",
            session_id=session_id,
            total_duration_ms=total_duration_ms,
            timing=timing,
            segments=segments,
            audio={},  # Audio refs are generated separately via voice script
            sets=sets
        )

        return manifest

    def _build_auto_sequence(
        self,
        duration_mins: int,
        focus: str,
        difficulty: str
    ) -> List[str]:
        """Build an automatic pose sequence based on parameters."""
        total_seconds = duration_mins * 60
        available_poses = list(self.poses.values())

        # Filter by focus
        if focus != "all":
            available_poses = [p for p in available_poses if focus in p.get("focus", [])]
            if not available_poses:
                available_poses = list(self.poses.values())

        # Sort by difficulty for phased approach
        beginner = [p for p in available_poses if p.get("difficulty") == "beginner"]
        intermediate = [p for p in available_poses if p.get("difficulty") == "intermediate"]
        advanced = [p for p in available_poses if p.get("difficulty") == "advanced"]

        sequence = []
        current_duration = 0

        # Warmup phase (20%) - beginner poses
        warmup_target = total_seconds * 0.2
        import random
        random.shuffle(beginner)
        for pose in beginner:
            if current_duration >= warmup_target:
                break
            sequence.append(pose["id"])
            current_duration += pose.get("duration_seconds", [30])[0]

        # Main phase (60%) - mix of difficulties
        main_target = total_seconds * 0.8
        main_poses = intermediate + advanced + beginner
        random.shuffle(main_poses)
        for pose in main_poses:
            if current_duration >= main_target:
                break
            if pose["id"] not in sequence:
                sequence.append(pose["id"])
                current_duration += pose.get("duration_seconds", [30])[0]

        # Cooldown phase (20%) - relaxation poses
        cooldown_poses = [
            p for p in available_poses
            if "relaxation" in p.get("focus", []) or p.get("category") == "seated"
        ]
        random.shuffle(cooldown_poses)
        for pose in cooldown_poses:
            if current_duration >= total_seconds:
                break
            if pose["id"] not in sequence:
                sequence.append(pose["id"])
                current_duration += pose.get("duration_seconds", [30])[0]

        return sequence

    def _build_segments(
        self,
        pose_sequence: List[str],
        session_style: str = "vinyasa"
    ) -> tuple[List[Dict], Dict[str, Dict]]:
        """
        Build segments from pose sequence with sequential bilateral flow.

        Flow: All poses RIGHT side first, then all poses LEFT side.
        This creates a continuous vinyasa flow without breaks.

        Args:
            pose_sequence: List of pose IDs
            session_style: "power" or "vinyasa" for timing adjustments

        Returns:
            Tuple of (segments list, sets dict)
        """
        style_config = SESSION_STYLES.get(session_style, SESSION_STYLES["vinyasa"])
        segments = []
        sets = {}
        segment_index = 0

        # Separate poses by type
        bilateral_poses = []
        symmetric_poses = []

        for pose_id in pose_sequence:
            pose = self.get_pose(pose_id)
            if not pose:
                _debug_log(f"[MANIFEST] Unknown pose: {pose_id}, skipping")
                continue

            symmetry_type = pose.get("symmetryType", "symmetric")
            if symmetry_type == "bilateral":
                bilateral_poses.append(pose)
            else:
                symmetric_poses.append(pose)

        _debug_log(f"[MANIFEST] Building flow: {len(bilateral_poses)} bilateral, {len(symmetric_poses)} symmetric")

        # === PHASE 1: RIGHT SIDE (all bilateral poses) ===
        right_segments = []
        for i, pose in enumerate(bilateral_poses):
            seg = self._generate_sided_segment(
                pose, segment_index, "right", session_style,
                is_first=(i == 0),
                is_last=(i == len(bilateral_poses) - 1),
                rotation="right"
            )
            right_segments.append(seg)
            segments.append(seg)
            segment_index += 1

        # === PHASE 2: LEFT SIDE (all bilateral poses, same order) ===
        left_segments = []
        for i, pose in enumerate(bilateral_poses):
            seg = self._generate_sided_segment(
                pose, segment_index, "left", session_style,
                is_first=(i == 0),
                is_last=(i == len(bilateral_poses) - 1),
                rotation="left"
            )
            left_segments.append(seg)
            segments.append(seg)
            segment_index += 1

        # === PHASE 3: SYMMETRIC POSES (if any, at the end as cooldown) ===
        for pose in symmetric_poses:
            seg = self._generate_single_segment(pose, segment_index, False, session_style)
            segments.append(seg)
            segment_index += 1

        # Build sets for tracking
        for i, pose in enumerate(bilateral_poses):
            set_id = f"set_{i}"
            sets[f"{set_id}_right"] = {
                "name": f"{pose['name']} (Right)",
                "side": "right",
                "segments": [right_segments[i]["index"]] if i < len(right_segments) else []
            }
            sets[f"{set_id}_left"] = {
                "name": f"{pose['name']} (Left)",
                "side": "left",
                "segments": [left_segments[i]["index"]] if i < len(left_segments) else []
            }

        # Add interpolation data for continuous flow
        self._add_interpolation_data(segments)

        # Mark the rotation switch point (only when switching from right to left)
        if right_segments and left_segments:
            # Left side start is the rotation switch
            left_segments[0]["isRotationStart"] = True
            left_segments[0]["rotationSide"] = "left"
            # Right side start is not a switch, just the beginning
            right_segments[0]["isRotationStart"] = False
            right_segments[0]["rotationSide"] = "right"

        return segments, sets

    def _generate_sided_segment(
        self,
        pose: Dict,
        index: int,
        side: str,
        session_style: str = "vinyasa",
        is_first: bool = False,
        is_last: bool = False,
        rotation: str = "right"
    ) -> Dict:
        """Generate a segment for a specific side (left or right)."""
        bilateral_data = generate_bilateral_pair(pose, base_side=side)

        # Get style and trait-based timing
        style_config = SESSION_STYLES.get(session_style, SESSION_STYLES["vinyasa"])
        trait_mods = get_trait_timing_modifier(pose, session_style)

        # Calculate hold duration with style multiplier and trait modifier
        base_duration = pose.get("duration_seconds", [30])[0] * 1000
        hold_duration = int(base_duration * style_config["holdMultiplier"] * trait_mods["hold"])

        # Calculate transition duration with trait modifier
        trans_duration = int(style_config["transitionDurationMs"] * trait_mods["transition"])

        return {
            "index": index,
            "type": "pose",
            "poseId": pose["id"],
            "side": side,
            "setId": f"set_{index}_{side}",
            "holdDurationMs": hold_duration,
            "isBridge": False,
            "isRotationStart": False,
            "rotationSide": rotation,
            "landmarks": {
                "active": bilateral_data["active"]["landmarks"],
                "mirrored": bilateral_data["mirrored"]["landmarks"]
            },
            "angles": {
                "active": bilateral_data["active"]["angles"],
                "mirrored": bilateral_data["mirrored"]["angles"]
            },
            "interpolation": {
                "fromIndex": None,
                "durationMs": trans_duration,
                "easing": "easeInOut"
            },
            "audioRefs": [],
            "name": pose.get("name", ""),
            "sanskrit": pose.get("sanskrit", ""),
            "instructions": pose.get("instructions", []),
            "image": pose.get("image", ""),
            "traits": pose.get("traits", {}),
            "isFirstInRotation": is_first,
            "isLastInRotation": is_last
        }

    def _generate_single_segment(
        self,
        pose: Dict,
        index: int,
        is_bridge: bool = False,
        session_style: str = "vinyasa"
    ) -> Dict:
        """Generate a single segment for a symmetric pose or bridge."""
        landmarks = pose.get("reference_landmarks", [])
        angles = pose.get("reference_angles", {})

        # For symmetric poses, active and mirrored are the same
        bilateral_data = generate_bilateral_pair(pose)

        # Get style and trait-based timing
        style_config = SESSION_STYLES.get(session_style, SESSION_STYLES["vinyasa"])
        trait_mods = get_trait_timing_modifier(pose, session_style)

        # Calculate hold duration with style multiplier and trait modifier
        base_duration = pose.get("duration_seconds", [30])[0] * 1000
        hold_duration = int(base_duration * style_config["holdMultiplier"] * trait_mods["hold"])

        if is_bridge:
            hold_duration = min(hold_duration, 15000)  # Bridges are shorter

        # Calculate transition duration with trait modifier
        trans_duration = int(style_config["transitionDurationMs"] * trait_mods["transition"])

        return {
            "index": index,
            "type": "bridge" if is_bridge else "pose",
            "poseId": pose["id"],
            "side": None,
            "setId": None,
            "holdDurationMs": hold_duration,
            "isBridge": is_bridge,
            "landmarks": {
                "active": landmarks,
                "mirrored": bilateral_data["mirrored"]["landmarks"]
            },
            "angles": {
                "active": angles,
                "mirrored": bilateral_data["mirrored"]["angles"]
            },
            "interpolation": {
                "fromIndex": None,
                "durationMs": trans_duration,
                "easing": "easeInOut"
            },
            "audioRefs": [],
            "name": pose.get("name", ""),
            "sanskrit": pose.get("sanskrit", ""),
            "instructions": pose.get("instructions", []),
            "image": pose.get("image", ""),
            "traits": pose.get("traits", {})  # Include traits for client-side use
        }

    def _generate_bilateral_segments(
        self,
        pose: Dict,
        start_index: int,
        set_counter: int,
        session_style: str = "vinyasa"
    ) -> tuple[Dict, Dict, Dict]:
        """Generate left and right segments for a bilateral pose."""
        bilateral_data = generate_bilateral_pair(pose, base_side="left")
        set_id = f"set_{set_counter}"

        # Get style and trait-based timing
        style_config = SESSION_STYLES.get(session_style, SESSION_STYLES["vinyasa"])
        trait_mods = get_trait_timing_modifier(pose, session_style)

        # Calculate hold duration with style multiplier and trait modifier
        base_duration = pose.get("duration_seconds", [30])[0] * 1000
        hold_duration = int(base_duration * style_config["holdMultiplier"] * trait_mods["hold"])

        # Calculate transition duration with trait modifier
        trans_duration = int(style_config["transitionDurationMs"] * trait_mods["transition"])

        # Left side segment (uses original landmarks)
        left_seg = {
            "index": start_index,
            "type": "pose",
            "poseId": pose["id"],
            "side": "left",
            "setId": f"{set_id}_left",
            "holdDurationMs": hold_duration,
            "isBridge": False,
            "landmarks": {
                "active": bilateral_data["active"]["landmarks"],
                "mirrored": bilateral_data["mirrored"]["landmarks"]
            },
            "angles": {
                "active": bilateral_data["active"]["angles"],
                "mirrored": bilateral_data["mirrored"]["angles"]
            },
            "interpolation": {
                "fromIndex": None,
                "durationMs": trans_duration,
                "easing": "easeInOut"
            },
            "audioRefs": [],
            "name": pose.get("name", ""),
            "sanskrit": pose.get("sanskrit", ""),
            "instructions": pose.get("instructions", []),
            "image": pose.get("image", ""),
            "traits": pose.get("traits", {})
        }

        # Right side segment (uses mirrored landmarks as active)
        right_seg = {
            "index": start_index + 1,
            "type": "pose",
            "poseId": pose["id"],
            "side": "right",
            "setId": f"{set_id}_right",
            "holdDurationMs": hold_duration,
            "isBridge": False,
            "landmarks": {
                "active": bilateral_data["mirrored"]["landmarks"],
                "mirrored": bilateral_data["active"]["landmarks"]
            },
            "angles": {
                "active": bilateral_data["mirrored"]["angles"],
                "mirrored": bilateral_data["active"]["angles"]
            },
            "interpolation": {
                "fromIndex": start_index,  # Interpolate from left side
                "durationMs": trans_duration,
                "easing": "easeInOut"
            },
            "audioRefs": [],
            "name": pose.get("name", ""),
            "sanskrit": pose.get("sanskrit", ""),
            "instructions": pose.get("instructions", []),
            "image": pose.get("image", ""),
            "traits": pose.get("traits", {})
        }

        set_info = {
            "name": pose.get("name", ""),
            "left_index": start_index,
            "right_index": start_index + 1
        }

        return left_seg, right_seg, set_info

    def _add_interpolation_data(self, segments: List[Dict]):
        """Add interpolation data linking consecutive segments."""
        for i in range(1, len(segments)):
            current = segments[i]
            prev = segments[i - 1]

            # Skip if already set (e.g., bilateral pairs)
            if current["interpolation"]["fromIndex"] is not None:
                continue

            current["interpolation"]["fromIndex"] = prev["index"]

            # Get transition duration from graph
            trans_ms = pose_graph.get_transition_duration_ms(
                prev["poseId"],
                current["poseId"]
            )
            current["interpolation"]["durationMs"] = trans_ms


# Singleton instance
manifest_generator = SessionManifestGenerator()


def generate_manifest(
    duration_mins: int,
    focus: str = "all",
    difficulty: str = "beginner",
    pose_ids: Optional[List[str]] = None,
    session_style: str = "vinyasa"
) -> Dict:
    """
    Main entry point: Generate a session manifest.

    Args:
        duration_mins: Target session duration
        focus: Focus area
        difficulty: Difficulty level
        pose_ids: Optional explicit pose list
        session_style: "power" for efficient workout, "vinyasa" for breath-centered

    Returns manifest as a dictionary ready for JSON serialization.
    """
    manifest = manifest_generator.generate(
        duration_mins=duration_mins,
        focus=focus,
        difficulty=difficulty,
        pose_ids=pose_ids,
        session_style=session_style
    )
    return manifest.to_dict()
