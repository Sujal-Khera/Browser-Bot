"""
browserbot.logging.logger — structured JSON logger factory.

Design decisions:
- One `get_logger(name)` function mirrors the standard `logging.getLogger` API.
- The root "browserbot" logger emits JSON records to stderr so they can be
  piped/parsed by external tools without interfering with stdout results.
- A Rich StreamHandler is attached to stdout for interactive sessions when
  the BROWSERBOT_LOG_JSON environment variable is NOT set to "1".
- Log level is controlled by the BROWSERBOT_LOG_LEVEL environment variable
  (default: INFO).

Structured extra fields logged alongside every record:
    component   — the logger name (set automatically)
    level       — log level string
    timestamp   — ISO-8601 UTC timestamp
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, MutableMapping


# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.

    Every record includes:
        timestamp  — ISO-8601 UTC
        level      — DEBUG / INFO / WARNING / ERROR / CRITICAL
        component  — logger name
        message    — formatted log message
        ...        — any extra fields passed via the `extra` kwarg
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields the caller supplied.
        skip: frozenset[str] = frozenset(
            logging.LogRecord(
                "", 0, "", 0, "", (), None  # type: ignore[arg-type]
            ).__dict__.keys()
        )
        for key, value in record.__dict__.items():
            if key not in skip and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


# ---------------------------------------------------------------------------
# Logger factory
# ---------------------------------------------------------------------------

_root_configured: bool = False


def _configure_root() -> None:
    """
    Configure the root "browserbot" logger once.

    Called lazily on the first `get_logger()` invocation.
    """
    global _root_configured  # noqa: PLW0603
    if _root_configured:
        return

    level_name: str = os.getenv("BROWSERBOT_LOG_LEVEL", "INFO").upper()
    level: int = getattr(logging, level_name, logging.INFO)

    root: logging.Logger = logging.getLogger("browserbot")
    root.setLevel(level)
    root.propagate = False  # don't bleed into the stdlib root logger

    use_json: bool = os.getenv("BROWSERBOT_LOG_JSON", "0") == "1"

    if use_json:
        # Machine-readable: JSON to stderr
        json_handler = logging.StreamHandler(sys.stderr)
        json_handler.setFormatter(_JsonFormatter())
        root.addHandler(json_handler)
    else:
        # Human-readable: plain text to stderr
        human_handler = logging.StreamHandler(sys.stderr)
        human_formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )
        human_handler.setFormatter(human_formatter)
        root.addHandler(human_handler)

    _root_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger namespaced under "browserbot.<name>".

    Args:
        name: Typically ``__name__`` of the calling module.

    Returns:
        A configured :class:`logging.Logger` instance.

    Example::

        log = get_logger(__name__)
        log.info("Recording started", extra={"session_id": "abc123"})
    """
    _configure_root()
    # Ensure name is always a child of the "browserbot" hierarchy.
    if not name.startswith("browserbot"):
        name = f"browserbot.{name}"
    return logging.getLogger(name)
