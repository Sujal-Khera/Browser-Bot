"""
browserbot.logging — structured JSON logging for every pipeline component.

Usage:
    from browserbot.logging import get_logger

    log = get_logger(__name__)
    log.info("Pipeline stage started", extra={"artifact": "actions.json"})

Every log record is emitted as JSON to stderr (machine-readable) and optionally
as a Rich-formatted line to stdout (human-readable) when running interactively.
"""

from browserbot.logging.logger import get_logger

__all__ = ["get_logger"]
