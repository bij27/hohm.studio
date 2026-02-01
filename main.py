import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
from api.routes import router as api_router
from api.websocket import router as ws_router
from models.database import init_db, close_pool, cleanup_old_sessions
from middleware.security import SecurityMiddleware, RequestValidationMiddleware, validate_websocket_origin
from websocket_manager import ws_manager
import asyncio
from yoga_voice import generate_session_voice_script
from services.session_manifest import generate_manifest
from services.audit_logger import ManifestValidator
from utils.network import get_client_ip
import os
import config as cfg


# Background task for data retention cleanup
_cleanup_task = None

async def _data_retention_cleanup():
    """Background task to periodically clean up old session data."""
    interval_hours = cfg.DATA_CLEANUP_INTERVAL_HOURS
    retention_days = cfg.DATA_RETENTION_DAYS

    while True:
        try:
            await asyncio.sleep(interval_hours * 3600)  # Convert hours to seconds
            deleted, error = await cleanup_old_sessions(retention_days)
            if error:
                if cfg.ENVIRONMENT == "development":
                    print(f"[CLEANUP] Error: {error}")
            elif deleted > 0 and cfg.ENVIRONMENT == "development":
                print(f"[CLEANUP] Removed {deleted} sessions older than {retention_days} days")
        except asyncio.CancelledError:
            break
        except Exception as e:
            if cfg.ENVIRONMENT == "development":
                print(f"[CLEANUP] Unexpected error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _cleanup_task
    # Startup
    await init_db()
    ws_manager.start_cleanup_task()  # Start room cleanup background task
    _cleanup_task = asyncio.create_task(_data_retention_cleanup())  # Start data retention cleanup
    yield
    # Shutdown
    if _cleanup_task:
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass
    await close_pool()


app = FastAPI(
    title="hohm.studio - AI Posture Correction",
    description='Your "ohm" at home. AI-powered posture correction for a healthier, more zen lifestyle.',
    version="1.0.0",
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url="/docs" if cfg.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if cfg.ENVIRONMENT == "development" else None,
    openapi_url="/openapi.json" if cfg.ENVIRONMENT == "development" else None,
)

# Security Middleware (applied first, runs last - wraps everything)
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestValidationMiddleware)

# Trusted Host Middleware (prevent host header attacks)
if cfg.ENVIRONMENT == "production" and cfg.ALLOWED_HOSTS:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=cfg.ALLOWED_HOSTS
    )

# CORS Configuration - More restrictive in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=cfg.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],  # Only methods we actually use
    allow_headers=["Content-Type", "Authorization"],  # Only headers we need
    max_age=600,  # Cache preflight for 10 minutes
)

# Health Check
@app.get("/health")
async def health_check():
    return {"status": "healthy", "environment": cfg.ENVIRONMENT}

# SEO & Ads files
@app.get("/robots.txt")
async def robots():
    return FileResponse("static/robots.txt", media_type="text/plain")

@app.get("/ads.txt")
async def ads():
    return FileResponse("static/ads.txt", media_type="text/plain")

@app.get("/security.txt")
@app.get("/.well-known/security.txt")
async def security_txt():
    return FileResponse("static/.well-known/security.txt", media_type="text/plain")

templates = Jinja2Templates(directory="templates")

@app.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/calibrate")
async def calibrate_page(request: Request):
    return templates.TemplateResponse("calibrate.html", {"request": request})

@app.get("/tos")
async def tos_page(request: Request):
    return templates.TemplateResponse("tos.html", {"request": request})

@app.get("/science")
async def science_page(request: Request):
    return templates.TemplateResponse("science.html", {"request": request})

@app.get("/app")
async def app_page(request: Request):
    return templates.TemplateResponse("app.html", {"request": request, "show_ads": False})

@app.get("/yoga")
async def yoga_page(request: Request):
    return templates.TemplateResponse("yoga.html", {"request": request})


def _load_poses_data():
    """Load poses data from JSON file."""
    import json
    poses_path = os.path.join("static", "data", "yoga", "poses.json")
    try:
        with open(poses_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if cfg.ENVIRONMENT == "development":
            print(f"[WARN] Poses data file not found: {poses_path}")
        return {"poses": []}
    except json.JSONDecodeError as e:
        if cfg.ENVIRONMENT == "development":
            print(f"[WARN] Invalid JSON in poses data: {e}")
        return {"poses": []}


def _load_knowledge_base():
    """Load knowledge base data from JSON file."""
    import json
    kb_path = os.path.join("static", "data", "yoga", "knowledge_base.json")
    try:
        with open(kb_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"poses": {}}


@app.get("/yoga/poses/{pose_id}")
async def yoga_pose_detail(request: Request, pose_id: str):
    """Detailed pose encyclopedia page."""
    # Load poses data
    poses_data = _load_poses_data()
    knowledge_base = _load_knowledge_base()

    # Find the requested pose
    pose = None
    for p in poses_data.get("poses", []):
        if p["id"] == pose_id:
            pose = p
            break

    if not pose:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/yoga", status_code=302)

    # Get knowledge base entry for this pose
    knowledge = knowledge_base.get("poses", {}).get(pose_id, None)

    # Get related poses (same category or focus)
    related_poses = [
        p for p in poses_data.get("poses", [])
        if p["id"] != pose_id and (
            p["category"] == pose["category"] or
            any(f in pose.get("focus", []) for f in p.get("focus", []))
        )
    ][:4]

    return templates.TemplateResponse("yoga_pose_detail.html", {
        "request": request,
        "pose": pose,
        "knowledge": knowledge,
        "related_poses": related_poses
    })

@app.get("/yoga/preview")
async def yoga_preview_page(request: Request):
    """Pre-session flow preview page with educational content."""
    return templates.TemplateResponse("yoga_flow_preview.html", {"request": request})


@app.get("/yoga/report")
async def yoga_report_page(request: Request):
    """Post-session wellness report page."""
    return templates.TemplateResponse("yoga_session_report.html", {"request": request})


@app.get("/yoga/session")
async def yoga_session_page(request: Request):
    return templates.TemplateResponse("yoga_session.html", {"request": request, "show_ads": False})

@app.get("/yoga/remote")
async def yoga_remote_entry(request: Request):
    return templates.TemplateResponse("yoga_remote_entry.html", {"request": request, "show_ads": False})

@app.get("/yoga/remote/{code}")
async def yoga_remote_page(request: Request, code: str):
    """Join a room via code (manual entry)."""
    code = code.strip().upper()
    if not ws_manager.room_exists(code):
        return templates.TemplateResponse("yoga_remote_entry.html", {
            "request": request,
            "show_ads": False,
            "error": "Room not found. Check the code and try again."
        })
    return templates.TemplateResponse("yoga_remote.html", {"request": request, "code": code, "show_ads": False})

@app.get("/yoga/join")
async def yoga_join_via_token(request: Request, token: str = ""):
    """Join a room via QR code token (secure, single-use)."""
    if not token:
        return templates.TemplateResponse("yoga_remote_entry.html", {
            "request": request,
            "show_ads": False,
            "error": "Invalid link. Please scan the QR code again or enter a code manually."
        })

    room, error = ws_manager.validate_token(token)
    if not room:
        return templates.TemplateResponse("yoga_remote_entry.html", {
            "request": request,
            "show_ads": False,
            "error": error
        })

    # Token valid - redirect to room
    return templates.TemplateResponse("yoga_remote.html", {"request": request, "code": room.code, "show_ads": False})

# Yoga Session WebSocket Endpoints
@app.post("/api/yoga/room")
async def create_yoga_room(request: Request):
    """Create a new yoga session room and return the code + token for QR."""
    room_info = ws_manager.create_room()

    # Build the QR URL with the secure token
    host = request.headers.get("host", "localhost")
    scheme = "https" if cfg.ENVIRONMENT == "production" else request.url.scheme
    qr_url = f"{scheme}://{host}/yoga/join?token={room_info['token']}"

    return JSONResponse({
        "code": room_info["code"],
        "token": room_info["token"],
        "qr_url": qr_url
    })

@app.post("/api/yoga/voice-script")
async def generate_voice_script(request: Request):
    """Generate voice script with audio URLs for a yoga session."""
    try:
        data = await request.json()

        # Debug logging only in development
        if cfg.ENVIRONMENT == "development":
            print(f"[VOICE] Duration: {data.get('duration')}, Focus: {data.get('focus')}, Poses: {len(data.get('poses', []))}")

        script = await generate_session_voice_script(data)

        if cfg.ENVIRONMENT == "development":
            print(f"[VOICE] Generated {len(script)} script items")

        return JSONResponse({"script": script})
    except Exception as e:
        if cfg.ENVIRONMENT == "development":
            print(f"[VOICE] Error generating script: {e}")
            return JSONResponse({"error": str(e), "script": []}, status_code=500)
        return JSONResponse({"error": "Voice generation temporarily unavailable", "script": []}, status_code=500)


@app.post("/api/yoga/manifest")
async def generate_session_manifest(request: Request):
    """
    Generate a v2.0 session manifest with segments, interpolation keyframes, and bilateral sets.

    Request body:
    {
        "duration": 15,           // Duration in minutes
        "focus": "all",           // Focus area (all, balance, flexibility, strength, relaxation)
        "difficulty": "beginner", // Difficulty level
        "poses": ["warrior", ...] // Optional: explicit pose list (overrides auto-generation)
        "style": "vinyasa"        // Session style: "power" or "vinyasa"
    }

    Returns:
    {
        "manifest": { ... },      // Full session manifest
        "valid": true,            // Pre-flight validation result
        "errors": []              // Validation errors if any
    }
    """
    data = await request.json()

    duration_mins = data.get("duration", 15)
    focus = data.get("focus", "all")
    difficulty = data.get("difficulty", "beginner")
    pose_ids = data.get("poses")  # Optional explicit pose list
    session_style = data.get("style", "vinyasa")  # Default to vinyasa

    if cfg.ENVIRONMENT == "development":
        print(f"[MANIFEST] Generating: {duration_mins}min, focus={focus}, difficulty={difficulty}, style={session_style}")

    # Generate the manifest
    manifest = generate_manifest(
        duration_mins=duration_mins,
        focus=focus,
        difficulty=difficulty,
        pose_ids=pose_ids,
        session_style=session_style
    )

    # Validate the manifest
    is_valid, errors = ManifestValidator.validate(manifest)

    if cfg.ENVIRONMENT == "development":
        print(f"[MANIFEST] Generated {len(manifest.get('segments', []))} segments, valid={is_valid}")
        if errors:
            for err in errors:
                print(f"[MANIFEST] Validation error: {err}")

    return JSONResponse({
        "manifest": manifest,
        "valid": is_valid,
        "errors": errors
    })

@app.get("/api/yoga/room/{code}")
async def check_yoga_room(request: Request, code: str):
    """Check if a room exists (with rate limiting)."""
    client_ip = get_client_ip(request)
    room, error = ws_manager.validate_code(code, client_ip)

    if error:
        # Generic error to avoid revealing validation details
        return JSONResponse({"exists": False}, status_code=404)

    return JSONResponse({"exists": True})

@app.websocket("/ws/yoga/desktop/{code}")
async def yoga_desktop_websocket(websocket: WebSocket, code: str):
    """WebSocket endpoint for desktop yoga session."""
    # Validate origin to prevent cross-site WebSocket hijacking
    if not validate_websocket_origin(websocket):
        await websocket.close(code=4000, reason="Connection rejected")
        return

    if not await ws_manager.connect_desktop(websocket, code):
        await websocket.close(code=4000, reason="Connection rejected")
        return

    try:
        while True:
            data = await websocket.receive_json()
            await ws_manager.handle_desktop_message(code, data)
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, code)
    except Exception:
        await ws_manager.disconnect(websocket, code)

@app.websocket("/ws/yoga/remote/{code}")
async def yoga_remote_websocket(websocket: WebSocket, code: str):
    """WebSocket endpoint for phone remote."""
    # Validate origin to prevent cross-site WebSocket hijacking
    if not validate_websocket_origin(websocket):
        await websocket.close(code=4000, reason="Connection rejected")
        return

    if not await ws_manager.connect_remote(websocket, code):
        await websocket.close(code=4000, reason="Connection rejected")
        return

    try:
        while True:
            data = await websocket.receive_json()
            await ws_manager.handle_remote_message(code, data)
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, code)
    except Exception as e:
        # Log errors only in development to avoid leaking info
        if cfg.ENVIRONMENT == "development":
            print(f"[WS] Remote error: {code} - {e}")
        await ws_manager.disconnect(websocket, code)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(api_router)
app.include_router(ws_router)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    reload = cfg.ENVIRONMENT == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
