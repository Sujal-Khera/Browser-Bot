"""
browserbot/server/app.py — FastAPI Orchestration Server application module.
"""

from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from browserbot.server.routes import sessions, packages
from browserbot.server.db import SessionStateStore

app = FastAPI(
    title="BrowserBot Local Orchestration Server",
    description="Local-first REST API backend orchestrating the BrowserBot Playwright-to-MCP generation pipeline.",
    version="0.1.0",
)

# Register sub-routers
app.include_router(sessions.router)
app.include_router(packages.router)


@app.on_event("startup")
def startup_event():
    """Initialises state storage and schema migrations on start."""
    SessionStateStore()


@app.get("/health", tags=["health"])
async def health_check():
    """Liveness probe. Returns 200 OK status."""
    return {"status": "ok"}


# Serve built static files from frontend/dist
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    # Mount assets directory for JS/CSS files
    if (frontend_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{catchall:path}", include_in_schema=False)
    async def serve_frontend(catchall: str):
        """SPA catch-all. Serves index.html for all non-API GET requests."""
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return {"message": "BrowserBot API is running. Frontend index.html not found."}

