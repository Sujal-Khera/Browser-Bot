"""
browserbot/server/__main__.py — FastAPI Orchestration Server entry point command.
"""

from __future__ import annotations

import uvicorn
from browserbot.server.config import server_config


def main() -> None:
    """Launch the FastAPI application server using uvicorn binding only to localhost."""
    uvicorn.run(
        "browserbot.server.app:app",
        host=server_config.host,
        port=server_config.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
