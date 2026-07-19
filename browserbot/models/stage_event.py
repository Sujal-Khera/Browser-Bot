"""
browserbot/models/stage_event.py — Observer and stage event model for pipeline progress tracking.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class StageEvent:
    """Represents a discrete status or progress transition event in the pipeline."""

    def __init__(
        self,
        stage: str,
        status: str,
        message: str,
        timestamp: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.stage = stage
        self.status = status
        self.message = message
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        self.metadata = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def get_base64_screenshot(path_str: str) -> str | None:
    """Reads a screenshot from disk and returns its base64-encoded string representation."""
    try:
        path = Path(path_str)
        if path.exists():
            return base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception as exc:
        log.warning("Failed to base64 encode screenshot", extra={"path": path_str, "error": str(exc)})
    return None
