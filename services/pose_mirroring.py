"""
Pose Mirroring Service
Utilities for mirroring landmarks and angles for bilateral symmetry support.
"""

from typing import Dict, List
from copy import deepcopy


# Mapping of left/right angle keys for swapping
ANGLE_SWAP_MAP = {
    "left_elbow_angle": "right_elbow_angle",
    "right_elbow_angle": "left_elbow_angle",
    "left_shoulder_angle": "right_shoulder_angle",
    "right_shoulder_angle": "left_shoulder_angle",
    "left_knee_angle": "right_knee_angle",
    "right_knee_angle": "left_knee_angle",
    "left_hip_angle": "right_hip_angle",
    "right_hip_angle": "left_hip_angle",
}

# MediaPipe landmark indices that need to be swapped for mirroring
# Left landmarks: 1-4 (left eye), 7 (left ear), 9 (mouth left), 11, 13, 15, 17, 19, 21 (left arm),
#                 23, 25, 27, 29, 31 (left leg)
# Right landmarks: 4-6 (right eye), 8 (right ear), 10 (mouth right), 12, 14, 16, 18, 20, 22 (right arm),
#                  24, 26, 28, 30, 32 (right leg)
LANDMARK_SWAP_PAIRS = [
    # Eyes
    (1, 4),   # LEFT_EYE_INNER <-> RIGHT_EYE_INNER
    (2, 5),   # LEFT_EYE <-> RIGHT_EYE
    (3, 6),   # LEFT_EYE_OUTER <-> RIGHT_EYE_OUTER
    # Ears
    (7, 8),   # LEFT_EAR <-> RIGHT_EAR
    # Mouth
    (9, 10),  # MOUTH_LEFT <-> MOUTH_RIGHT
    # Shoulders
    (11, 12), # LEFT_SHOULDER <-> RIGHT_SHOULDER
    # Elbows
    (13, 14), # LEFT_ELBOW <-> RIGHT_ELBOW
    # Wrists
    (15, 16), # LEFT_WRIST <-> RIGHT_WRIST
    # Pinky
    (17, 18), # LEFT_PINKY <-> RIGHT_PINKY
    # Index
    (19, 20), # LEFT_INDEX <-> RIGHT_INDEX
    # Thumb
    (21, 22), # LEFT_THUMB <-> RIGHT_THUMB
    # Hips
    (23, 24), # LEFT_HIP <-> RIGHT_HIP
    # Knees
    (25, 26), # LEFT_KNEE <-> RIGHT_KNEE
    # Ankles
    (27, 28), # LEFT_ANKLE <-> RIGHT_ANKLE
    # Heels
    (29, 30), # LEFT_HEEL <-> RIGHT_HEEL
    # Foot index
    (31, 32), # LEFT_FOOT_INDEX <-> RIGHT_FOOT_INDEX
]


def mirror_landmarks(landmarks: List[Dict]) -> List[Dict]:
    """
    Mirror landmarks by flipping X coordinates and swapping left/right pairs.

    The mirroring formula: mirrored_x = 1.0 - original_x

    Args:
        landmarks: List of landmark dicts with x, y, z, and optionally visibility

    Returns:
        New list of mirrored landmarks
    """
    if not landmarks:
        return []

    # Deep copy to avoid mutating original
    mirrored = deepcopy(landmarks)

    # First, flip all X coordinates
    for landmark in mirrored:
        if "x" in landmark:
            landmark["x"] = 1.0 - landmark["x"]

    # Then swap left/right landmark pairs
    for left_idx, right_idx in LANDMARK_SWAP_PAIRS:
        if left_idx < len(mirrored) and right_idx < len(mirrored):
            mirrored[left_idx], mirrored[right_idx] = mirrored[right_idx], mirrored[left_idx]

    return mirrored


def mirror_angles(angles: Dict[str, float]) -> Dict[str, float]:
    """
    Mirror angle dictionary by swapping left/right keys.

    Args:
        angles: Dict of angle name -> value

    Returns:
        New dict with swapped keys
    """
    if not angles:
        return {}

    mirrored = {}
    for key, value in angles.items():
        # Swap the key if it's in our mapping
        new_key = ANGLE_SWAP_MAP.get(key, key)
        mirrored[new_key] = value

    return mirrored


def generate_bilateral_pair(pose_data: Dict, base_side: str = "left") -> Dict:
    """
    Generate a bilateral pair with both active and mirrored data.

    Args:
        pose_data: Original pose data with reference_landmarks and reference_angles
        base_side: Which side the original pose data represents ("left" or "right")

    Returns:
        Dict containing both original and mirrored versions:
        {
            "active": { "landmarks": [...], "angles": {...} },
            "mirrored": { "landmarks": [...], "angles": {...} },
            "baseSide": "left"
        }
    """
    landmarks = pose_data.get("reference_landmarks", [])
    angles = pose_data.get("reference_angles", {})

    # Generate mirrored versions
    mirrored_landmarks = mirror_landmarks(landmarks)
    mirrored_angles = mirror_angles(angles)

    return {
        "active": {
            "landmarks": landmarks,
            "angles": angles
        },
        "mirrored": {
            "landmarks": mirrored_landmarks,
            "angles": mirrored_angles
        },
        "baseSide": base_side
    }


def get_side_landmarks(bilateral_data: Dict, side: str) -> List[Dict]:
    """
    Get landmarks for a specific side from bilateral data.

    Args:
        bilateral_data: Output from generate_bilateral_pair()
        side: "left" or "right"

    Returns:
        Landmarks for the requested side
    """
    base_side = bilateral_data.get("baseSide", "left")

    if side == base_side:
        return bilateral_data.get("active", {}).get("landmarks", [])
    else:
        return bilateral_data.get("mirrored", {}).get("landmarks", [])


def get_side_angles(bilateral_data: Dict, side: str) -> Dict[str, float]:
    """
    Get angles for a specific side from bilateral data.

    Args:
        bilateral_data: Output from generate_bilateral_pair()
        side: "left" or "right"

    Returns:
        Angles for the requested side
    """
    base_side = bilateral_data.get("baseSide", "left")

    if side == base_side:
        return bilateral_data.get("active", {}).get("angles", {})
    else:
        return bilateral_data.get("mirrored", {}).get("angles", {})
