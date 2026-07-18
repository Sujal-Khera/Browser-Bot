"""
browserbot/server/config.py — FastAPI Orchestration Server Configuration.
"""

from __future__ import annotations

import os
from pathlib import Path


class ServerConfig:
    """FastAPI server configurations loaded from environment variables."""

    def __init__(self) -> None:
        self._db_path: Path | None = None

    @property
    def host(self) -> str:
        """Host to bind to. Strictly limited to loopback for security."""
        return "127.0.0.1"

    @property
    def port(self) -> int:
        """Port to bind to. Configurable via BROWSERBOT_SERVER_PORT, default 8765."""
        return int(os.getenv("BROWSERBOT_SERVER_PORT", "8765"))

    @property
    def db_path(self) -> Path:
        """SQLite metadata store path. Defaults to ~/.browserbot/state.db."""
        if self._db_path is not None:
            return self._db_path
        default_dir = Path.home() / ".browserbot"
        default_dir.mkdir(parents=True, exist_ok=True)
        return Path(os.getenv("BROWSERBOT_STATE_DB_PATH", str(default_dir / "state.db")))

    @db_path.setter
    def db_path(self, val: Path) -> None:
        self._db_path = val


server_config = ServerConfig()

