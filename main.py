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
from models.database import init_db, close_pool
from middleware.security import SecurityMiddleware, RequestValidationMiddleware
from websocket_manager import ws_manager
from yoga_voice import generate_session_voice_script
import os
import config as cfg


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    ws_manager.start_cleanup_task()  # Start room cleanup background task
    yield
    # Shutdown
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

templates = Jinja2Templates(directory="templates")

@app.get("/privacy")
async def privacy_page(request: Request):
    return templates.TemplateResponse("privacy.html", {"request": request})

@app.get("/app")
async def app_page(request: Request):
    return templates.TemplateResponse("app.html", {"request": request})

@app.get("/yoga")
async def yoga_page(request: Request):
    return templates.TemplateResponse("yoga.html", {"request": request})

@app.get("/yoga/session")
async def yoga_session_page(request: Request):
    return templates.TemplateResponse("yoga_session.html", {"request": request})

@app.get("/yoga/remote")
async def yoga_remote_entry(request: Request):
    return templates.TemplateResponse("yoga_remote_entry.html", {"request": request})

@app.get("/yoga/remote/{code}")
async def yoga_remote_page(request: Request, code: str):
    if not ws_manager.room_exists(code):
        return templates.TemplateResponse("yoga_remote_entry.html", {
            "request": request,
            "error": "Room not found. Check the code and try again."
        })
    return templates.TemplateResponse("yoga_remote.html", {"request": request, "code": code})

# Yoga Session WebSocket Endpoints
@app.post("/api/yoga/room")
async def create_yoga_room():
    """Create a new yoga session room and return the code."""
    code = ws_manager.create_room()
    return JSONResponse({"code": code})

@app.post("/api/yoga/voice-script")
async def generate_voice_script(request: Request):
    """Generate voice script with audio URLs for a yoga session."""
    data = await request.json()

    # Debug: Log received data
    print(f"\n[VOICE] ========== RECEIVED SESSION DATA ==========")
    print(f"[VOICE] Duration: {data.get('duration')}, Focus: {data.get('focus')}")
    print(f"[VOICE] Poses received: {len(data.get('poses', []))}")
    for i, pose in enumerate(data.get('poses', [])):
        instructions = pose.get('instructions', [])
        print(f"[VOICE] Pose {i}: {pose.get('name')} - {len(instructions)} instructions")
        for j, inst in enumerate(instructions):
            print(f"  [{j}]: {inst[:50]}...")
    print(f"[VOICE] ================================================\n")

    script = await generate_session_voice_script(data)

    # Debug: Log script breakdown
    print(f"[VOICE] Generated {len(script)} items")
    by_pose = {}
    by_type = {}
    for item in script:
        pose_idx = item.get('pose_index', 'session')
        by_pose[pose_idx] = by_pose.get(pose_idx, 0) + 1
        item_type = item.get('type', 'unknown')
        by_type[item_type] = by_type.get(item_type, 0) + 1
    print(f"[VOICE] By pose: {by_pose}")
    print(f"[VOICE] By type: {by_type}")

    return JSONResponse({"script": script})

@app.get("/api/yoga/room/{code}")
async def check_yoga_room(code: str):
    """Check if a room exists."""
    exists = ws_manager.room_exists(code)
    return JSONResponse({"exists": exists})

@app.websocket("/ws/yoga/desktop/{code}")
async def yoga_desktop_websocket(websocket: WebSocket, code: str):
    """WebSocket endpoint for desktop yoga session."""
    if not await ws_manager.connect_desktop(websocket, code):
        await websocket.close(code=4004, reason="Room not found")
        return

    try:
        while True:
            data = await websocket.receive_json()
            await ws_manager.handle_desktop_message(code, data)
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, code)
    except Exception:
        await ws_manager.disconnect(websocket, code)

# Remote WebSocket handler with debug logging
@app.websocket("/ws/yoga/remote/{code}")
async def yoga_remote_websocket(websocket: WebSocket, code: str):
    """WebSocket endpoint for phone remote."""
    if not await ws_manager.connect_remote(websocket, code):
        await websocket.close(code=4004, reason="Room not found")
        return

    try:
        while True:
            data = await websocket.receive_json()
            print(f"[MAIN] Received from remote: {data}", flush=True)
            await ws_manager.handle_remote_message(code, data)
    except WebSocketDisconnect:
        print(f"[MAIN] Remote disconnected: {code}", flush=True)
        await ws_manager.disconnect(websocket, code)
    except Exception as e:
        print(f"[MAIN] Remote error: {code} - {e}", flush=True)
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
