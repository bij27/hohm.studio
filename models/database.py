import asyncpg
import config as cfg
import json
import math
import traceback
from typing import Optional, Any

# Constants
MAX_LOGS_PER_SESSION = 10000

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


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
    """Clamp a number to valid range, return default if invalid or NaN/Infinity."""
    try:
        num = float(value)
        # Check for NaN or Infinity
        if math.isnan(num) or math.isinf(num):
            return default
        return max(min_val, min(max_val, num))
    except (TypeError, ValueError):
        return default


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        import ssl
        # Create SSL context for Supabase
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE  # Supabase uses self-signed certs via pooler

        # Supabase pooler requires statement_cache_size=0 to disable prepared statements
        _pool = await asyncpg.create_pool(
            cfg.DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=30,
            statement_cache_size=0,  # Required for Supabase transaction pooler
            ssl=ssl_context
        )
        print("[DB] Connection pool created successfully")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def init_db():
    """Initialize database with required tables and indexes."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Create sessions table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    start_time TIMESTAMPTZ,
                    end_time TIMESTAMPTZ,
                    duration_minutes REAL,
                    good_posture_percentage REAL,
                    average_score REAL,
                    total_logs INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')

            # Create logs table
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    id SERIAL PRIMARY KEY,
                    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
                    timestamp TIMESTAMPTZ,
                    status TEXT,
                    score REAL,
                    issues JSONB,
                    metrics JSONB,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            ''')

            # Create index for faster queries by session_id
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_logs_session_id ON logs(session_id)
            ''')

            print("[DB] Database initialized successfully")
            return True
    except Exception as e:
        print(f"[DB] Failed to initialize database: {e}")
        return False


async def session_exists(session_id: str) -> bool:
    """Check if a session already exists in the database."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT 1 FROM sessions WHERE id = $1 LIMIT 1',
                session_id
            )
            return row is not None
    except Exception:
        return False


async def save_session(session_data: dict) -> tuple[bool, str]:
    """
    Save session to database with validation.
    Returns (success, error_message).
    """
    print(f"[DB] save_session called with data: {session_data}")

    # Validate data
    is_valid, error = _validate_session_data(session_data)
    if not is_valid:
        print(f"[DB] Session validation failed: {error}")
        return False, error

    session_id = session_data['session_id']
    print(f"[DB] Attempting to save session: {session_id}")

    try:
        # Check for duplicate
        if await session_exists(session_id):
            print(f"[DB] Session {session_id} already exists, skipping")
            return True, "Session already saved"

        # Sanitize numeric values
        duration = _sanitize_number(session_data['duration_minutes'], 0, 1440, 0)
        percentage = _sanitize_number(session_data['good_posture_percentage'], 0, 100, 0)
        score = _sanitize_number(session_data['average_score'], 0, 10, 0)
        logs = int(_sanitize_number(session_data['total_logs'], 0, MAX_LOGS_PER_SESSION, 0))

        print(f"[DB] Sanitized values - duration: {duration}, percentage: {percentage}, score: {score}, logs: {logs}")

        pool = await get_pool()
        print(f"[DB] Got pool, acquiring connection...")
        async with pool.acquire() as conn:
            print(f"[DB] Connection acquired, executing INSERT...")
            result = await conn.execute('''
                INSERT INTO sessions
                (id, start_time, end_time, duration_minutes, good_posture_percentage, average_score, total_logs)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO NOTHING
            ''',
                session_id,
                session_data['start_time'],
                session_data['end_time'],
                round(duration, 2),
                round(percentage, 2),
                round(score, 2),
                logs
            )
            print(f"[DB] INSERT result: {result}")
            return True, ""

    except asyncpg.UniqueViolationError:
        # Duplicate key - not really an error
        print(f"[DB] Session {session_id} duplicate")
        return True, "Session already saved"
    except Exception as e:
        print(f"[DB] Failed to save session: {e}")
        print(f"[DB] Traceback: {traceback.format_exc()}")
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

        # Sanitize issues and metrics (ensure they're valid for JSONB)
        try:
            issues = log_data.get('issues', [])
            if not isinstance(issues, list):
                issues = []
        except (TypeError, ValueError):
            issues = []

        try:
            metrics = log_data.get('metrics', {})
            if not isinstance(metrics, dict):
                metrics = {}
        except (TypeError, ValueError):
            metrics = {}

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO logs (session_id, timestamp, status, score, issues, metrics)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''',
                log_data['session_id'],
                log_data['timestamp'],
                str(log_data.get('status', 'unknown'))[:20],  # Limit status length
                round(score, 2),
                json.dumps(issues),
                json.dumps(metrics)
            )
            return True, ""

    except Exception as e:
        print(f"[DB] Failed to save log: {e}")
        return False, str(e)


async def get_all_sessions() -> list[dict]:
    """Retrieve all sessions, ordered by start time descending."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, start_time, end_time, duration_minutes,
                       good_posture_percentage, average_score, total_logs
                FROM sessions
                ORDER BY start_time DESC
            ''')
            return [dict(row) for row in rows]
    except Exception as e:
        print(f"[DB] Failed to get sessions: {e}")
        return []


async def get_session(session_id: str) -> Optional[dict]:
    """Retrieve a single session by ID."""
    if not session_id or not isinstance(session_id, str):
        return None

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                '''SELECT id, start_time, end_time, duration_minutes,
                          good_posture_percentage, average_score, total_logs
                   FROM sessions WHERE id = $1''',
                session_id
            )
            return dict(row) if row else None
    except Exception as e:
        print(f"[DB] Failed to get session {session_id}: {e}")
        return None


async def get_session_logs(session_id: str) -> list[dict]:
    """Retrieve all logs for a session."""
    if not session_id or not isinstance(session_id, str):
        return []

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                '''SELECT id, session_id, timestamp, status, score, issues, metrics
                   FROM logs WHERE session_id = $1 ORDER BY timestamp''',
                session_id
            )
            result = []
            for row in rows:
                row_dict = dict(row)
                # Parse JSONB fields back to Python objects
                if row_dict.get('issues'):
                    try:
                        row_dict['issues'] = json.loads(row_dict['issues']) if isinstance(row_dict['issues'], str) else row_dict['issues']
                    except json.JSONDecodeError:
                        row_dict['issues'] = []
                if row_dict.get('metrics'):
                    try:
                        row_dict['metrics'] = json.loads(row_dict['metrics']) if isinstance(row_dict['metrics'], str) else row_dict['metrics']
                    except json.JSONDecodeError:
                        row_dict['metrics'] = {}
                result.append(row_dict)
            return result
    except Exception as e:
        print(f"[DB] Failed to get logs for session {session_id}: {e}")
        return []


async def delete_session(session_id: str) -> bool:
    """Delete a session and its logs."""
    if not session_id or not isinstance(session_id, str):
        return False

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Logs are deleted automatically via CASCADE
            result = await conn.execute(
                'DELETE FROM sessions WHERE id = $1',
                session_id
            )
            return 'DELETE 1' in result
    except Exception as e:
        print(f"[DB] Failed to delete session {session_id}: {e}")
        return False


async def clear_all_sessions() -> bool:
    """Delete all sessions and logs."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Logs are deleted automatically via CASCADE
            await conn.execute('DELETE FROM sessions')
            return True
    except Exception as e:
        print(f"[DB] Failed to clear sessions: {e}")
        return False
