import aiosqlite
import os
import config as cfg
import json
from typing import Optional, Dict, Any


class DatabaseError(Exception):
    """Custom exception for database operations."""
    pass


def _validate_session_data(session_data: dict) -> tuple[bool, str]:
    """
    Validate session data before saving.
    Returns (is_valid, error_message).
    """
    required_fields = ['session_id', 'start_time', 'end_time', 'duration_minutes',
                       'good_posture_percentage', 'average_score', 'total_logs']

    # Check required fields
    for field in required_fields:
        if field not in session_data:
            return False, f"Missing required field: {field}"

    # Validate session_id format (UUID)
    session_id = session_data['session_id']
    if not session_id or not isinstance(session_id, str) or len(session_id) < 10:
        return False, "Invalid session_id format"

    # Validate numeric ranges
    duration = session_data.get('duration_minutes', 0)
    if not isinstance(duration, (int, float)) or duration < 0 or duration > 1440:  # Max 24 hours
        return False, f"Invalid duration_minutes: {duration}"

    percentage = session_data.get('good_posture_percentage', 0)
    if not isinstance(percentage, (int, float)) or percentage < 0 or percentage > 100:
        return False, f"Invalid good_posture_percentage: {percentage}"

    score = session_data.get('average_score', 0)
    if not isinstance(score, (int, float)) or score < 0 or score > 10:
        return False, f"Invalid average_score: {score}"

    logs = session_data.get('total_logs', 0)
    if not isinstance(logs, int) or logs < 0:
        return False, f"Invalid total_logs: {logs}"

    return True, ""


def _sanitize_number(value: Any, min_val: float, max_val: float, default: float) -> float:
    """Clamp a number to valid range, return default if invalid."""
    try:
        num = float(value)
        return max(min_val, min(max_val, num))
    except (TypeError, ValueError):
        return default


async def init_db():
    """Initialize database with required tables and indexes."""
    try:
        os.makedirs(os.path.dirname(cfg.DB_PATH), exist_ok=True)

        async with aiosqlite.connect(cfg.DB_PATH) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    start_time TEXT,
                    end_time TEXT,
                    duration_minutes REAL,
                    good_posture_percentage REAL,
                    average_score REAL,
                    total_logs INTEGER
                )
            ''')
            await db.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    timestamp TEXT,
                    status TEXT,
                    score REAL,
                    issues TEXT,
                    metrics TEXT,
                    screenshot_path TEXT,
                    FOREIGN KEY(session_id) REFERENCES sessions(id)
                )
            ''')
            # Add index for faster queries by session_id
            await db.execute('''
                CREATE INDEX IF NOT EXISTS idx_logs_session_id ON logs(session_id)
            ''')
            await db.commit()
            return True
    except Exception as e:
        print(f"[DB] Failed to initialize database: {e}")
        return False


async def session_exists(session_id: str) -> bool:
    """Check if a session already exists in the database."""
    try:
        async with aiosqlite.connect(cfg.DB_PATH) as db:
            cursor = await db.execute(
                'SELECT 1 FROM sessions WHERE id = ? LIMIT 1',
                (session_id,)
            )
            row = await cursor.fetchone()
            return row is not None
    except Exception:
        return False


async def save_session(session_data: dict) -> tuple[bool, str]:
    """
    Save session to database with validation.
    Returns (success, error_message).
    """
    # Validate data
    is_valid, error = _validate_session_data(session_data)
    if not is_valid:
        print(f"[DB] Session validation failed: {error}")
        return False, error

    session_id = session_data['session_id']

    try:
        # Check for duplicate
        if await session_exists(session_id):
            print(f"[DB] Session {session_id} already exists, skipping")
            return True, "Session already saved"

        # Sanitize numeric values
        duration = _sanitize_number(session_data['duration_minutes'], 0, 1440, 0)
        percentage = _sanitize_number(session_data['good_posture_percentage'], 0, 100, 0)
        score = _sanitize_number(session_data['average_score'], 0, 10, 0)
        logs = int(_sanitize_number(session_data['total_logs'], 0, 1000000, 0))

        async with aiosqlite.connect(cfg.DB_PATH) as db:
            await db.execute('''
                INSERT OR IGNORE INTO sessions
                (id, start_time, end_time, duration_minutes, good_posture_percentage, average_score, total_logs)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                session_id,
                session_data['start_time'].isoformat(),
                session_data['end_time'].isoformat(),
                round(duration, 2),
                round(percentage, 2),
                round(score, 2),
                logs
            ))
            await db.commit()
            return True, ""

    except aiosqlite.IntegrityError as e:
        # Duplicate key - not really an error
        print(f"[DB] Session {session_id} duplicate: {e}")
        return True, "Session already saved"
    except Exception as e:
        print(f"[DB] Failed to save session: {e}")
        return False, str(e)


async def save_log(log_data: dict) -> tuple[bool, str]:
    """
    Save log entry to database with validation.
    Returns (success, error_message).
    """
    required_fields = ['session_id', 'timestamp', 'status', 'score']

    # Check required fields
    for field in required_fields:
        if field not in log_data:
            return False, f"Missing required field: {field}"

    try:
        # Sanitize score
        score = _sanitize_number(log_data.get('score', 0), 0, 10, 0)

        # Sanitize issues and metrics (ensure they're valid JSON)
        try:
            issues = json.dumps(log_data.get('issues', []))
        except (TypeError, ValueError):
            issues = '[]'

        try:
            metrics = json.dumps(log_data.get('metrics', {}))
        except (TypeError, ValueError):
            metrics = '{}'

        async with aiosqlite.connect(cfg.DB_PATH) as db:
            await db.execute('''
                INSERT INTO logs (session_id, timestamp, status, score, issues, metrics, screenshot_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                log_data['session_id'],
                log_data['timestamp'].isoformat(),
                str(log_data.get('status', 'unknown'))[:20],  # Limit status length
                round(score, 2),
                issues,
                metrics,
                log_data.get('screenshot_path', '')
            ))
            await db.commit()
            return True, ""

    except Exception as e:
        print(f"[DB] Failed to save log: {e}")
        return False, str(e)


async def get_all_sessions() -> list[dict]:
    """Retrieve all sessions, ordered by start time descending."""
    try:
        async with aiosqlite.connect(cfg.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute('''
                SELECT * FROM sessions ORDER BY start_time DESC
            ''')
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Failed to get sessions: {e}")
        return []


async def get_session(session_id: str) -> Optional[dict]:
    """Retrieve a single session by ID."""
    if not session_id or not isinstance(session_id, str):
        return None

    try:
        async with aiosqlite.connect(cfg.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM sessions WHERE id = ?',
                (session_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    except Exception as e:
        print(f"[DB] Failed to get session {session_id}: {e}")
        return None


async def get_session_logs(session_id: str) -> list[dict]:
    """Retrieve all logs for a session."""
    if not session_id or not isinstance(session_id, str):
        return []

    try:
        async with aiosqlite.connect(cfg.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                'SELECT * FROM logs WHERE session_id = ? ORDER BY timestamp',
                (session_id,)
            )
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Failed to get logs for session {session_id}: {e}")
        return []
