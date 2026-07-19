"""
browserbot/orchestrator/events.py — Proxy module for stage events to prevent circular imports.
"""

from __future__ import annotations

from browserbot.models.stage_event import StageEvent, get_base64_screenshot

__all__ = [
    "StageEvent",
    "get_base64_screenshot",
]
