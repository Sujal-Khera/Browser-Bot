"""
browserbot/runtime/result_formatter.py — Step 6.4: Tool result formatting.

Provides the two public functions used by every BrowserBot-generated tool:

    format_success(outputs: dict) -> str
    format_error(exc_message: str | None) -> str

These functions are the only place where raw browser-extraction data or
Python exception text is converted to a form suitable for Claude Desktop
to relay conversationally.

CONTRACT
--------
- Both functions always return a non-empty ``str``.
- Neither function ever raises.
- ``format_success`` never returns raw JSON.
- ``format_error`` never exposes Python tracebacks, file paths, or
  raw exception class names.
- The first sentence of ``format_error`` MUST start with the sentinel::

      "I wasn't able to complete the workflow"

  This sentinel is checked by ``DryRunHarness`` to distinguish error
  prose from success prose.  Do NOT change it without updating harness.py.

USAGE IN GENERATED SERVERS
---------------------------
The Jinja2 template (server.py.j2) imports and calls these functions
directly so that the formatting logic is testable outside of Playwright.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Error sentinel — must match the check in harness.py exactly
# ---------------------------------------------------------------------------

_ERROR_SENTINEL = "I wasn't able to complete the workflow"

# ---------------------------------------------------------------------------
# Prefixes to strip from raw exception strings before surfacing them
# ---------------------------------------------------------------------------

_STRIP_PREFIXES = (
    "Workflow execution failed: ",
    "TimeoutError: ",
    "Error: ",
    "Exception: ",
    "RuntimeError: ",
    "playwright._impl._errors.TimeoutError: ",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_success(outputs: dict) -> str:
    """
    Convert an output extraction dict into a conversational, human-readable
    string that Claude can relay directly without further processing.

    Args:
        outputs: Dict mapping output-key names (snake_case) to extracted
                 string values.  May be empty.

    Returns:
        A non-empty human-readable string.  Never raises.
    """
    try:
        if not outputs:
            return "The workflow completed successfully. No data was extracted."

        lines = ["The workflow completed successfully.\n"]
        for key, value in outputs.items():
            # snake_case → Title Case
            label = str(key).replace("_", " ").title()
            str_value = str(value).strip() if value is not None else "(empty)"
            lines.append(f"• {label}: {str_value}")
        return "\n".join(lines)
    except Exception:  # pragma: no cover — belt-and-suspenders
        return "The workflow completed successfully."


def format_error(exc_message: str | None) -> str:
    """
    Convert a raw exception message into a clean, user-friendly error string
    that Claude can relay conversationally.

    The returned string ALWAYS starts with ``_ERROR_SENTINEL`` so that
    ``DryRunHarness`` can detect error returns via a simple prefix check.

    Args:
        exc_message: Raw exception string (may include traceback lines,
                     file paths, etc.).  May be None or empty.

    Returns:
        A non-empty human-readable error sentence.  Never raises.
    """
    try:
        raw = str(exc_message or "").strip()

        # Strip noisy traceback preamble — keep only the last meaningful line
        if "Traceback (most recent call last)" in raw:
            # Take the last non-empty line (usually the actual exception)
            lines = [l.strip() for l in raw.splitlines() if l.strip()]
            raw = lines[-1] if lines else raw

        # Strip known verbose prefixes
        clean = raw
        for prefix in _STRIP_PREFIXES:
            if clean.startswith(prefix):
                clean = clean[len(prefix):]

        # Truncate excessively long messages so they read naturally in chat
        max_chars = 200
        if len(clean) > max_chars:
            clean = clean[:max_chars].rsplit(" ", 1)[0] + "…"

        clean = clean.strip() or "an unexpected error occurred"

        return (
            f"{_ERROR_SENTINEL} right now. "
            f"Reason: {clean} "
            "Please try again in a moment, or check that the target site is reachable."
        )
    except Exception:  # pragma: no cover — belt-and-suspenders
        return (
            f"{_ERROR_SENTINEL} right now. "
            "An unexpected error occurred. "
            "Please try again in a moment."
        )
