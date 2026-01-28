from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import os
import json
import re
import aiosqlite
import config as cfg
from models.schemas import CalibrationProfile
from models.database import get_all_sessions, get_session, get_session_logs
from services.report_generator import ReportGenerator

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
async def dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(request: Request):
    return templates.TemplateResponse("sessions.html", {"request": request})


@router.get("/review/{session_id}", response_class=HTMLResponse)
async def review(request: Request, session_id: str):
    # Strict UUID validation to prevent XSS and injection
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
    return templates.TemplateResponse("review.html", {"request": request, "session_id": session_id})


# === Profile API ===

@router.get("/api/profile")
async def api_get_profile():
    if not os.path.exists(cfg.PROFILE_PATH):
        raise HTTPException(status_code=404, detail="Profile not found")
    try:
        with open(cfg.PROFILE_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise HTTPException(status_code=500, detail="Failed to read profile")


@router.post("/api/profile")
async def api_save_profile(profile: CalibrationProfile):
    try:
        import aiofiles
        os.makedirs(cfg.DATA_DIR, exist_ok=True)
        async with aiofiles.open(cfg.PROFILE_PATH, "w") as f:
            await f.write(profile.json())
        return {"status": "success"}
    except IOError as e:
        raise HTTPException(status_code=500, detail="Failed to save profile")


# === Sessions API ===

@router.get("/api/sessions")
async def api_list_sessions():
    sessions = await get_all_sessions()
    return sessions


@router.get("/api/sessions/{session_id}")
async def api_get_session(session_id: str):
    # Strict UUID validation
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    logs = await get_session_logs(session_id)

    # Generate analysis
    try:
        common_issues = ReportGenerator.identify_common_issues(logs)
        recommendations = ReportGenerator.get_recommendations(common_issues)
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
async def api_delete_session(session_id: str):
    # Strict UUID validation
    if not validate_session_id(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    try:
        async with aiosqlite.connect(cfg.DB_PATH) as db:
            # Check if session exists
            cursor = await db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Session not found")

            # Delete session and related logs
            await db.execute("DELETE FROM logs WHERE session_id = ?", (session_id,))
            await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            await db.commit()

        # Clean up screenshots for this session (with path traversal protection)
        try:
            real_screenshot_dir = os.path.realpath(cfg.SCREENSHOT_DIR)
            for f in os.listdir(cfg.SCREENSHOT_DIR):
                if f.startswith(session_id):
                    filepath = os.path.join(cfg.SCREENSHOT_DIR, f)
                    # Verify file is within screenshot directory
                    real_filepath = os.path.realpath(filepath)
                    if real_filepath.startswith(real_screenshot_dir) and os.path.isfile(real_filepath):
                        os.remove(real_filepath)
        except OSError:
            pass  # Non-critical

        return {"status": "success"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete session")


@router.get("/api/sessions/{session_id}/export")
async def api_export_session(session_id: str):
    data = await api_get_session(session_id)
    return JSONResponse(content=data)


@router.post("/api/sessions/clear")
async def api_clear_all_sessions():
    try:
        async with aiosqlite.connect(cfg.DB_PATH) as db:
            await db.execute("DELETE FROM logs")
            await db.execute("DELETE FROM sessions")
            await db.commit()

        # Clear screenshots (with path traversal protection)
        try:
            if os.path.exists(cfg.SCREENSHOT_DIR):
                real_screenshot_dir = os.path.realpath(cfg.SCREENSHOT_DIR)
                for f in os.listdir(cfg.SCREENSHOT_DIR):
                    filepath = os.path.join(cfg.SCREENSHOT_DIR, f)
                    real_filepath = os.path.realpath(filepath)
                    # Only delete files within the screenshot directory
                    if real_filepath.startswith(real_screenshot_dir) and os.path.isfile(real_filepath):
                        os.remove(real_filepath)
        except OSError:
            pass  # Non-critical

        return {"status": "success"}

    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to clear sessions")
