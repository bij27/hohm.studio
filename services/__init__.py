"""
Services package for hohm.studio yoga sessions.
Provides manifest generation, pose mirroring, transition graphs, and audit logging.
"""

from services.session_manifest import generate_manifest, SessionManifestGenerator
from services.pose_mirroring import mirror_landmarks, mirror_angles, generate_bilateral_pair
from services.pose_graph import PoseGraph, pose_graph
from services.audit_logger import SessionAuditLogger, ManifestValidator, create_audit_logger

__all__ = [
    # Manifest generation
    'generate_manifest',
    'SessionManifestGenerator',
    # Pose mirroring
    'mirror_landmarks',
    'mirror_angles',
    'generate_bilateral_pair',
    # Pose graph
    'PoseGraph',
    'pose_graph',
    # Audit logging
    'SessionAuditLogger',
    'ManifestValidator',
    'create_audit_logger',
]
