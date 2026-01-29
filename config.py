import os

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use environment variables directly

# Base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database - Supabase PostgreSQL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

# Posture Thresholds
FORWARD_HEAD_THRESHOLD_CM = 5.0
SHOULDER_ASYMMETRY_THRESHOLD_CM = 2.0
SLOUCH_ANGLE_THRESHOLD_DEG = 15.0
NECK_TILT_THRESHOLD_DEG = 20.0
SCREEN_DISTANCE_THRESHOLD_PCT = 30.0

# Scoring Constants
SCORE_START = 10.0
SCORE_MIN = 0.0

# Alert Persistence
CONSECUTIVE_BAD_POSTURE_SECONDS = 5
DETECTION_INTERVAL_SECONDS = 2
FPS_LIMIT = 10

# Security
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# CORS - Restrict in production
if ENVIRONMENT == "production":
    # In production, set specific origins via environment variable
    _origins = os.getenv("ALLOWED_ORIGINS", "")
    ALLOWED_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()]
    if not ALLOWED_ORIGINS:
        ALLOWED_ORIGINS = []  # Block all if not configured
else:
    # Development: allow all for testing
    ALLOWED_ORIGINS = ["*"]

# Trusted hosts - prevent host header attacks
_hosts = os.getenv("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]
# Always allow localhost during development or testing
if "localhost" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("localhost")
if "127.0.0.1" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("127.0.0.1")
if "0.0.0.0" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("0.0.0.0")
# In development, allow local network IPs for mobile testing
if ENVIRONMENT == "development":
    ALLOWED_HOSTS.append("*")

# Rate limiting
RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv("RATE_LIMIT_RPM", "120"))
RATE_LIMIT_BURST = int(os.getenv("RATE_LIMIT_BURST", "30"))

# Session security
_default_secret = "dev-secret-change-in-production"
_session_secret = os.getenv("SESSION_SECRET_KEY", _default_secret)

# Validate secret key security
if ENVIRONMENT == "production":
    if _session_secret == _default_secret:
        raise ValueError(
            "CRITICAL: SESSION_SECRET_KEY is using the default value in production! "
            "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    if len(_session_secret) < 32:
        raise ValueError(
            f"CRITICAL: SESSION_SECRET_KEY must be at least 32 characters (got {len(_session_secret)}). "
            "Generate a secure key with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
elif _session_secret == _default_secret:
    import warnings
    warnings.warn(
        "Using default SESSION_SECRET_KEY - this is fine for development but must be changed in production",
        UserWarning
    )

SESSION_SECRET_KEY = _session_secret
COOKIE_SECURE = ENVIRONMENT == "production"
COOKIE_HTTPONLY = True
COOKIE_SAMESITE = "strict"

# Data retention policy (GDPR/privacy compliance)
# Sessions older than this will be automatically deleted
DATA_RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "90"))  # Default 90 days
DATA_CLEANUP_INTERVAL_HOURS = int(os.getenv("DATA_CLEANUP_INTERVAL_HOURS", "24"))  # Run daily
