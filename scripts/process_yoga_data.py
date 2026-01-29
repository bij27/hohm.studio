"""
Process yoga pose dataset and create reference data for the app.
Extracts median landmarks and angles from the dataset to create
ideal reference poses for pose matching.
"""

import csv
import json
import os
from pathlib import Path
from statistics import median

# Pose metadata (manually curated)
POSE_METADATA = {
    "ArdhaChandrasana": {
        "name": "Half Moon",
        "sanskrit": "Ardha Chandrasana",
        "category": "standing",
        "difficulty": "intermediate",
        "duration_seconds": [30, 60],
        "focus": ["balance", "strength"],
        "instructions": [
            "Stand on one leg with the other extended behind you",
            "Reach one arm to the ground and the other toward the sky",
            "Keep your hips stacked and open your chest",
            "Gaze upward toward your raised hand"
        ],
        "benefits": "Improves balance, strengthens legs and core, stretches hamstrings"
    },
    "BaddhaKonasana": {
        "name": "Butterfly",
        "sanskrit": "Baddha Konasana",
        "category": "seated",
        "difficulty": "beginner",
        "duration_seconds": [45, 90],
        "focus": ["flexibility", "relaxation"],
        "instructions": [
            "Sit with the soles of your feet together",
            "Let your knees drop toward the floor",
            "Hold your feet with your hands",
            "Lengthen your spine and relax your shoulders"
        ],
        "benefits": "Opens hips, stretches inner thighs, calms the mind"
    },
    "Downward_dog": {
        "name": "Downward Dog",
        "sanskrit": "Adho Mukha Svanasana",
        "category": "inversion",
        "difficulty": "beginner",
        "duration_seconds": [30, 60],
        "focus": ["strength", "flexibility"],
        "instructions": [
            "Start on hands and knees",
            "Lift your hips up and back",
            "Press your heels toward the floor",
            "Keep your arms straight and head between your biceps"
        ],
        "benefits": "Stretches hamstrings and calves, strengthens arms, energizes the body"
    },
    "Natarajasana": {
        "name": "Dancer",
        "sanskrit": "Natarajasana",
        "category": "standing",
        "difficulty": "advanced",
        "duration_seconds": [30, 45],
        "focus": ["balance", "flexibility"],
        "instructions": [
            "Stand on one leg",
            "Grab your back foot with your hand",
            "Kick your foot into your hand while leaning forward",
            "Extend your free arm forward for balance"
        ],
        "benefits": "Improves balance, opens chest and shoulders, strengthens legs"
    },
    "Triangle": {
        "name": "Triangle",
        "sanskrit": "Trikonasana",
        "category": "standing",
        "difficulty": "beginner",
        "duration_seconds": [30, 60],
        "focus": ["flexibility", "strength"],
        "instructions": [
            "Stand with feet wide apart",
            "Turn one foot out 90 degrees",
            "Reach toward that foot while keeping both legs straight",
            "Extend your other arm toward the sky"
        ],
        "benefits": "Stretches legs and torso, strengthens core, improves stability"
    },
    "UtkataKonasana": {
        "name": "Goddess",
        "sanskrit": "Utkata Konasana",
        "category": "standing",
        "difficulty": "beginner",
        "duration_seconds": [30, 60],
        "focus": ["strength", "flexibility"],
        "instructions": [
            "Stand with feet wide, toes pointed outward",
            "Bend your knees deeply over your toes",
            "Keep your spine straight and core engaged",
            "Bring arms to goal post position or prayer"
        ],
        "benefits": "Strengthens legs and glutes, opens hips, builds heat"
    },
    "Veerabhadrasana": {
        "name": "Warrior",
        "sanskrit": "Virabhadrasana",
        "category": "standing",
        "difficulty": "beginner",
        "duration_seconds": [30, 60],
        "focus": ["strength", "balance"],
        "instructions": [
            "Step one foot back into a lunge",
            "Bend your front knee over your ankle",
            "Keep your back leg straight",
            "Raise your arms overhead or to the sides"
        ],
        "benefits": "Strengthens legs, opens hips and chest, builds stamina"
    },
    "Vrukshasana": {
        "name": "Tree",
        "sanskrit": "Vrksasana",
        "category": "standing",
        "difficulty": "beginner",
        "duration_seconds": [30, 60],
        "focus": ["balance", "relaxation"],
        "instructions": [
            "Stand on one leg",
            "Place your other foot on your inner thigh or calf",
            "Never place your foot on your knee",
            "Bring hands to prayer or raise overhead"
        ],
        "benefits": "Improves balance, strengthens legs, promotes focus"
    }
}

# Key angles to extract for pose matching
KEY_ANGLES = [
    "left_elbow_angle",
    "right_elbow_angle",
    "left_shoulder_angle",
    "right_shoulder_angle",
    "left_knee_angle",
    "right_knee_angle",
    "left_hip_angle",
    "right_hip_angle"
]


def extract_median_angles(csv_path):
    """Extract median angles from a pose angles CSV file."""
    angles = {key: [] for key in KEY_ANGLES}

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key in KEY_ANGLES:
                if key in row and row[key]:
                    try:
                        angles[key].append(float(row[key]))
                    except ValueError:
                        pass

    # Calculate median for each angle
    median_angles = {}
    for key, values in angles.items():
        if values:
            median_angles[key] = round(median(values), 2)
        else:
            median_angles[key] = None

    return median_angles


def extract_median_landmarks(csv_path):
    """Extract median landmarks from a pose landmarks CSV file."""
    # MediaPipe landmark names
    landmark_names = [
        "NOSE", "LEFT_EYE_INNER", "LEFT_EYE", "LEFT_EYE_OUTER",
        "RIGHT_EYE_INNER", "RIGHT_EYE", "RIGHT_EYE_OUTER",
        "LEFT_EAR", "RIGHT_EAR", "MOUTH_LEFT", "MOUTH_RIGHT",
        "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
        "LEFT_WRIST", "RIGHT_WRIST", "LEFT_PINKY", "RIGHT_PINKY",
        "LEFT_INDEX", "RIGHT_INDEX", "LEFT_THUMB", "RIGHT_THUMB",
        "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
        "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL",
        "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX"
    ]

    landmarks_data = {name: {"x": [], "y": [], "z": []} for name in landmark_names}

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            for name in landmark_names:
                for coord in ["x", "y", "z"]:
                    key = f"{name}_{coord}"
                    if key in row and row[key]:
                        try:
                            landmarks_data[name][coord].append(float(row[key]))
                        except ValueError:
                            pass

    # Calculate median for each landmark coordinate
    median_landmarks = []
    for name in landmark_names:
        landmark = {"name": name}
        for coord in ["x", "y", "z"]:
            values = landmarks_data[name][coord]
            if values:
                landmark[coord] = round(median(values), 6)
            else:
                landmark[coord] = 0
        median_landmarks.append(landmark)

    return median_landmarks


def process_all_poses(results_dir, output_path):
    """Process all pose CSVs and create the final JSON."""
    poses = []

    for pose_key, metadata in POSE_METADATA.items():
        # Find the CSV files for this pose
        angles_file = None
        landmarks_file = None

        for filename in os.listdir(results_dir):
            if filename.endswith("_Angles.csv") and pose_key.lower() in filename.lower():
                angles_file = os.path.join(results_dir, filename)
            elif filename.endswith(".csv") and not filename.endswith("_Angles.csv"):
                if pose_key.lower() in filename.lower():
                    landmarks_file = os.path.join(results_dir, filename)

        if not angles_file or not landmarks_file:
            print(f"Warning: Missing files for {pose_key}")
            continue

        print(f"Processing {pose_key}...")

        # Extract data
        angles = extract_median_angles(angles_file)
        landmarks = extract_median_landmarks(landmarks_file)

        # Create pose object
        pose = {
            "id": pose_key.lower().replace("_", "-"),
            **metadata,
            "reference_angles": angles,
            "reference_landmarks": landmarks
        }

        poses.append(pose)

    # Create final output
    output = {
        "version": "1.0",
        "pose_count": len(poses),
        "poses": poses
    }

    # Write JSON
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\nCreated {output_path} with {len(poses)} poses")


if __name__ == "__main__":
    script_dir = Path(__file__).parent.parent
    results_dir = script_dir / "_yoga_dataset_temp" / "Results"
    output_path = script_dir / "static" / "data" / "yoga" / "poses.json"

    # Create output directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    process_all_poses(str(results_dir), str(output_path))
