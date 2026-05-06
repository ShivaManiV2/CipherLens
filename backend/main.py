"""
CipherLens — FastAPI Application Entry Point

Initializes the app, registers middleware, mounts routers,
and creates database tables on startup.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.api import auth, documents, ml, security
from backend.config import APP_DESCRIPTION, APP_NAME, APP_VERSION
from backend.db.init_db import init_db

# ─── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)

# ─── Application ──────────────────────────────────────────
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS Middleware ──────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(ml.router)
app.include_router(security.router)


# ─── Startup ──────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    """Create all database tables if they don't already exist."""
    init_db()
    logging.getLogger(__name__).info(
        f"🚀 {APP_NAME} v{APP_VERSION} started — "
        f"ML Intelligence endpoints active at /api/ml/"
    )


# ─── Health Check ─────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    """Simple health-check endpoint for monitoring / load balancers."""
    return {
        "status": "healthy",
        "app": APP_NAME,
        "version": APP_VERSION,
    }


# ─── Serve Frontend (temporary) ──────────────────────────
# Will be replaced by a proper Next.js build in Phase 3.
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
