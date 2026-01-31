"""
Pose Graph Service
Manages pose transition graph for smooth flow sequencing with bridge pose injection.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from utils.debug import debug_log as _debug_log


@dataclass
class Transition:
    """Represents a transition between two poses."""
    from_pose: str
    to_pose: str
    cost: int
    bridge: Optional[str]
    transition_ms: int


class PoseGraph:
    """Graph-based pose transition manager with bridge injection."""

    def __init__(self, transitions_path: Optional[Path] = None):
        """Initialize the pose graph from transitions.json."""
        if transitions_path is None:
            transitions_path = Path("static/data/yoga/transitions.json")

        self.transitions: Dict[str, Dict[str, Transition]] = {}
        self.categories: Dict[str, List[str]] = {}
        self.category_transitions: Dict[str, Dict] = {}
        self.pose_id_mapping: Dict[str, str] = {}
        self.reverse_id_mapping: Dict[str, str] = {}

        self._load_graph(transitions_path)

    def _load_graph(self, path: Path):
        """Load transition graph from JSON file."""
        try:
            with open(path) as f:
                data = json.load(f)

            self.categories = data.get("categories", {})
            self.category_transitions = data.get("categoryTransitions", {})
            self.pose_id_mapping = data.get("poseIdMapping", {})

            # Build reverse mapping
            self.reverse_id_mapping = {v: k for k, v in self.pose_id_mapping.items()}

            # Build transition graph
            transitions_data = data.get("transitions", {})
            for from_pose, targets in transitions_data.items():
                self.transitions[from_pose] = {}
                for to_pose, trans_info in targets.items():
                    self.transitions[from_pose][to_pose] = Transition(
                        from_pose=from_pose,
                        to_pose=to_pose,
                        cost=trans_info.get("cost", 5),
                        bridge=trans_info.get("bridge"),
                        transition_ms=trans_info.get("transitionMs", 3000)
                    )

            _debug_log(f"[GRAPH] Loaded {len(self.transitions)} pose transitions")

        except FileNotFoundError:
            _debug_log(f"[GRAPH] Transitions file not found at {path}, using defaults")
            self._create_default_graph()
        except json.JSONDecodeError as e:
            _debug_log(f"[GRAPH] Error parsing transitions.json: {e}")
            self._create_default_graph()

    def _create_default_graph(self):
        """Create a minimal default graph if file is missing."""
        default_poses = ["warrior", "tree", "triangle", "downward-dog", "butterfly"]
        for from_pose in default_poses:
            self.transitions[from_pose] = {}
            for to_pose in default_poses:
                if from_pose != to_pose:
                    self.transitions[from_pose][to_pose] = Transition(
                        from_pose=from_pose,
                        to_pose=to_pose,
                        cost=5,
                        bridge=None,
                        transition_ms=3000
                    )

    def normalize_pose_id(self, pose_id: str) -> str:
        """Convert full pose ID (e.g., 'veerabhadrasana') to short name (e.g., 'warrior')."""
        return self.pose_id_mapping.get(pose_id, pose_id)

    def get_full_pose_id(self, short_name: str) -> str:
        """Convert short name (e.g., 'warrior') to full pose ID (e.g., 'veerabhadrasana')."""
        return self.reverse_id_mapping.get(short_name, short_name)

    def get_pose_category(self, pose_id: str) -> Optional[str]:
        """Get the category of a pose."""
        short_name = self.normalize_pose_id(pose_id)
        for category, poses in self.categories.items():
            if short_name in poses:
                return category
        return None

    def get_transition(self, from_pose: str, to_pose: str) -> Optional[Transition]:
        """Get transition info between two poses."""
        from_short = self.normalize_pose_id(from_pose)
        to_short = self.normalize_pose_id(to_pose)

        if from_short in self.transitions:
            return self.transitions[from_short].get(to_short)
        return None

    def get_transition_cost(self, from_pose: str, to_pose: str) -> int:
        """Get the cost of transitioning between two poses."""
        trans = self.get_transition(from_pose, to_pose)
        return trans.cost if trans else 10  # High default cost for unknown transitions

    def get_transition_duration_ms(self, from_pose: str, to_pose: str) -> int:
        """Get the transition duration in milliseconds."""
        trans = self.get_transition(from_pose, to_pose)
        return trans.transition_ms if trans else 3000

    def needs_bridge(self, from_pose: str, to_pose: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a bridge pose is needed between two poses.

        Returns:
            Tuple of (needs_bridge: bool, bridge_pose_id: Optional[str])
        """
        trans = self.get_transition(from_pose, to_pose)
        if trans and trans.bridge:
            return True, self.get_full_pose_id(trans.bridge)
        return False, None

    def get_bridge_pose(self, from_category: str, to_category: str) -> Optional[str]:
        """Get a bridge pose for transitioning between categories."""
        key = f"{from_category}_to_{to_category}"
        if key in self.category_transitions:
            bridge = self.category_transitions[key].get("bridge")
            return self.get_full_pose_id(bridge) if bridge else None
        return None

    def optimize_sequence(self, poses: List[str]) -> List[str]:
        """
        Optimize a pose sequence by injecting bridge poses where needed.

        Args:
            poses: List of pose IDs in order

        Returns:
            Optimized list with bridge poses inserted
        """
        if len(poses) < 2:
            return poses

        optimized = [poses[0]]

        for i in range(1, len(poses)):
            from_pose = poses[i - 1]
            to_pose = poses[i]

            needs, bridge = self.needs_bridge(from_pose, to_pose)
            if needs and bridge:
                _debug_log(f"[GRAPH] Injecting bridge {bridge} between {from_pose} and {to_pose}")
                optimized.append(bridge)

            optimized.append(to_pose)

        return optimized

    def calculate_total_transition_time(self, poses: List[str]) -> int:
        """Calculate total transition time for a sequence in milliseconds."""
        total_ms = 0
        for i in range(1, len(poses)):
            total_ms += self.get_transition_duration_ms(poses[i - 1], poses[i])
        return total_ms


# Singleton instance
pose_graph = PoseGraph()
