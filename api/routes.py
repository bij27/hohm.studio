from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import re
from models.database import (
    get_all_sessions, get_session, get_session_logs,
    delete_session, get_pool
)
from services.report_generator import ReportGenerator
from middleware.auth import require_device_token, generate_device_token, TOKEN_HEADER

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# UUID v4 pattern for session ID validation
UUID_PATTERN = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$', re.IGNORECASE)


def validate_session_id(session_id: str) -> bool:
    """Validate session ID is a valid UUID v4 format."""
    if not session_id or len(session_id) > 50:
        return False
    return bool(UUID_PATTERN.match(session_id))


# === Page Routes ===

@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/app", response_class=HTMLResponse)
async def dashboard(request: Request):
    return templates.TemplateResponse("app.html", {"request": request})


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    return templates.TemplateResponse("sessions.html", {"request": request})


@router.get("/review/{session_id}", response_class=HTMLResponse)
async def review(request: Request, session_id: str):
    # Strict UUID validation to prevent XSS and injection
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="Not found")
    return templates.TemplateResponse("review.html", {"request": request, "session_id": session_id})


# === Device Token API ===

@router.post("/api/auth/device-token")
async def create_device_token():
    """Generate a new device token for anonymous authentication."""
    token = generate_device_token()
    return JSONResponse(
        content={"token": token},
        headers={TOKEN_HEADER: token}
    )


# === Sessions API ===

@router.get("/api/sessions")
async def api_list_sessions(request: Request):
    """List all sessions for the authenticated device."""
    device_token = require_device_token(request)
    sessions = await get_all_sessions(device_token)
    return sessions


@router.get("/api/sessions/{session_id}")
async def api_get_session(request: Request, session_id: str):
    """Get a specific session (must belong to authenticated device)."""
    device_token = require_device_token(request)

    # Strict UUID validation
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="Not found")

    session = await get_session(session_id, device_token)
    if not session:
        raise HTTPException(status_code=404, detail="Not found")

    logs = await get_session_logs(session_id)

    # Generate analysis
    try:
        common_issues = ReportGenerator.identify_common_issues(logs)
        recommendations = ReportGenerator.get_recommendations(
            common_issues,
            good_posture_percentage=session.get('good_posture_percentage'),
            average_score=session.get('average_score')
        )
    except Exception:
        common_issues = []
        recommendations = []

    return {
        "session": session,
        "logs": logs,
        "common_issues": common_issues,
        "recommendations": recommendations
    }


@router.delete("/api/sessions/{session_id}")
async def api_delete_session(request: Request, session_id: str):
    """Delete a session (must belong to authenticated device)."""
    device_token = require_device_token(request)

    # Strict UUID validation
    if not validate_session_id(session_id):
        raise HTTPException(status_code=404, detail="Not found")

    # Check if session exists and belongs to this device
    session = await get_session(session_id, device_token)
    if not session:
        raise HTTPException(status_code=404, detail="Not found")

    # Delete session (logs are deleted via CASCADE)
    success = await delete_session(session_id, device_token)
    if not success:
        raise HTTPException(status_code=500, detail="Operation failed")

    return {"status": "success"}


@router.get("/api/sessions/{session_id}/export")
async def api_export_session(request: Request, session_id: str):
    """Export session data (must belong to authenticated device)."""
    # This reuses the auth check from api_get_session
    data = await api_get_session(request, session_id)
    return JSONResponse(content=data)


# NOTE: Mass deletion endpoint (/api/sessions/clear) was removed for security.
# To clear all sessions, use Supabase Dashboard directly:
# SQL: DELETE FROM sessions;  (logs cascade automatically)


@router.get("/api/db-health")
async def db_health_check(request: Request):
    """
    Check database connectivity and table existence.
    NOTE: In production, this endpoint returns minimal info to avoid information leakage.
    """
    import config as cfg

    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            # Test basic connectivity
            result = await conn.fetchval("SELECT 1")

            # Check if tables exist
            sessions_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'sessions')"
            )
            logs_exists = await conn.fetchval(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'logs')"
            )

            # In production, return minimal info to avoid information leakage
            if cfg.ENVIRONMENT == "production":
                return {
                    "status": "healthy",
                    "connected": result == 1
                }

            # In development, include detailed info for debugging
            session_count = await conn.fetchval("SELECT COUNT(*) FROM sessions") if sessions_exists else 0
            log_count = await conn.fetchval("SELECT COUNT(*) FROM logs") if logs_exists else 0

            return {
                "status": "healthy",
                "connected": result == 1,
                "tables": {
                    "sessions": sessions_exists,
                    "logs": logs_exists
                },
                "counts": {
                    "sessions": session_count,
                    "logs": log_count
                }
            }
    except Exception as e:
        # In production, don't leak error details
        if cfg.ENVIRONMENT == "production":
            return {"status": "error"}

        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }
