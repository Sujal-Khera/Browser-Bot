"""
browserbot/server/routes/packages.py — REST API router for managing package actions.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from browserbot.models.package import BrowserBotPackage
from browserbot.runtime.registry import ClaudeDesktopRegistry
from browserbot.server.schemas import RegisterRequest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/packages", tags=["packages"])


@router.post("/{name}/register")
async def register_package(name: str, req: RegisterRequest):
    """Registers a compiled package with the Claude Desktop configuration."""
    package_dir = Path("packages") / name
    pkg_manifest_path = package_dir / "browserbot_package.json"
    
    if not pkg_manifest_path.exists():
        # Fallback search if the package directory is customized
        raise HTTPException(
            status_code=404, 
            detail=f"Package manifest browserbot_package.json not found under packages/{name}."
        )

    try:
        pkg = BrowserBotPackage.from_file(pkg_manifest_path)
        registry_path = Path(req.registry_config_path) if req.registry_config_path else None
        
        registry = ClaudeDesktopRegistry(config_path=registry_path)
        config = registry.register(pkg)
        return config
    except Exception as exc:
        log.error("Failed to register package with Claude Desktop", extra={"package": name, "error": str(exc)})
        raise HTTPException(status_code=500, detail=f"Registration failed: {exc}")


@router.get("/{name}/upgrade-status")
async def get_package_upgrade_status(name: str):
    """Returns the version compatibility and upgrade status of a package."""
    package_dir = Path("packages") / name
    if not package_dir.exists():
        raise HTTPException(status_code=404, detail=f"Package directory packages/{name} not found.")

    from browserbot.version import detect_package_upgrade
    status = detect_package_upgrade(package_dir)
    return status.model_dump(mode="json")
