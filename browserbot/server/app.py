"""
browserbot/server/app.py — FastAPI Orchestration Server application module.
"""

from __future__ import annotations

from fastapi import FastAPI
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
