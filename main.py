import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from api.routes import router as api_router
from api.websocket import router as ws_router
from models.database import init_db
from middleware.security import SecurityMiddleware, RequestValidationMiddleware
import os
import config as cfg

app = FastAPI(
    title="hohm.studio - AI Posture Correction",
    description="Your ohm at home. AI-powered posture correction for a healthier, more zen lifestyle.",
    version="1.0.0",
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

@app.get("/privacy")
async def privacy_page(request: Request):
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="templates")
    return templates.TemplateResponse("privacy.html", {"request": request})

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount data screenshots
os.makedirs(cfg.SCREENSHOT_DIR, exist_ok=True)
app.mount("/static/data/screenshots", StaticFiles(directory=cfg.SCREENSHOT_DIR), name="screenshots")

# Include routers
app.include_router(api_router)
app.include_router(ws_router)

@app.on_event("startup")
async def startup_event():
    os.makedirs(cfg.DATA_DIR, exist_ok=True)
    os.makedirs(cfg.SCREENSHOT_DIR, exist_ok=True)
    await init_db()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    reload = cfg.ENVIRONMENT == "development"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=reload)
