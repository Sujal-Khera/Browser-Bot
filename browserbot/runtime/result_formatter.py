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
# Error category patterns — checked in order; first match wins.
# Each entry: (pattern_fragments, user_category, recovery_hint)
# ---------------------------------------------------------------------------

_ERROR_CATEGORIES = [
    # Timeout — covers Playwright TimeoutError, 30000ms exceeded, etc.
    (
        ("timeout", "30000ms", "exceeded waiting", "timed out"),
        "timeout",
        (
            "The page took too long to respond. "
            "This often happens when the target site is slow or a UI element did not appear in time. "
            "Please try again in a moment, or check that the site is loading normally."
        ),
    ),
    # Element / selector not found — strict mode violation, element not found, no element
    (
        ("strict mode violation", "element not found", "no element matches", "locator.click", "selector not found", "locator.fill"),
        "selector_not_found",
        (
            "A page element that the workflow depends on could not be located. "
            "The site's layout may have changed. "
            "Consider re-recording the workflow to capture the updated selectors."
        ),
    ),
    # Navigation / page load failure
    (
        ("net::err_", "err_connection", "err_name_not_resolved", "navigation failed", "failed to navigate", "page.goto"),
        "navigation_failed",
        (
            "The workflow could not navigate to the target page. "
            "Please verify that the site URL is correct and that your internet connection is active."
        ),
    ),
    # Network / connection error
    (
        ("connection refused", "connection reset", "network error", "econnrefused", "econnreset", "socket hang up"),
        "network_error",
        (
            "A network error interrupted the workflow. "
            "Please check that the target site is reachable and try again."
        ),
    ),
    # Authentication / permission error
    (
        ("403", "401", "unauthorized", "forbidden", "access denied", "login required"),
        "auth_error",
        (
            "The workflow was blocked by an authentication or permission check. "
            "You may need to log in first, or your session may have expired."
        ),
    ),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _classify_error(raw: str) -> str | None:
    """
    Return a user-friendly recovery sentence for a known error category, or
    ``None`` if no category matches (caller falls back to generic message).

    Pattern matching is case-insensitive and fragment-based so it is robust
    to minor wording differences across Playwright versions.
    """
    lower = raw.lower()
    for fragments, _category, recovery in _ERROR_CATEGORIES:
        if any(frag in lower for frag in fragments):
            return recovery
    return None


def _build_prose_sentence(key: str, value: str) -> str:
    """
    Convert a single snake_case key + value pair into a natural English clause.
    Slot-filling only — no grammar engine, no LLM.

    Examples
    --------
    ``order_status``, ``"Delivered"``  →  ``"order status is Delivered"``
    ``estimated_delivery``, ``"July 20"``  →  ``"estimated delivery is July 20"``
    """
    label = key.replace("_", " ").lower()
    return f"{label} is {value}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_success(outputs: dict, *, style: str = "bullet") -> str:
    """
    Convert an output extraction dict into a conversational, human-readable
    string that Claude can relay directly without further processing.

    Args:
        outputs: Dict mapping output-key names (snake_case) to extracted
                 string values.  May be empty.
        style:   ``"bullet"`` (default) — preserves the v1 bullet-list format
                 used by all previously generated ``server.py`` files.
                 ``"prose"`` — assembles a natural prose sentence from the
                 extraction results.  Used by the Jinja2 template for newly
                 generated tools (opt-in so existing packages are unaffected).

    Returns:
        A non-empty human-readable string.  Never raises.
    """
    try:
        if not outputs:
            return "The workflow completed successfully. No data was extracted."

        if style == "prose":
            return _format_success_prose(outputs)

        # Default: bullet list (v1 contract — must not change)
        lines = ["The workflow completed successfully.\n"]
        for key, value in outputs.items():
            # snake_case → Title Case
            label = str(key).replace("_", " ").title()
            str_value = str(value).strip() if value is not None else "(empty)"
            lines.append(f"• {label}: {str_value}")
        return "\n".join(lines)
    except Exception:  # pragma: no cover — belt-and-suspenders
        return "The workflow completed successfully."


def _format_success_prose(outputs: dict) -> str:
    """
    Assemble a natural prose summary for a single- or multi-output dict.
    Called only when ``style="prose"`` is requested; keeps ``format_success``
    uncluttered.
    """
    items = []
    for key, value in outputs.items():
        str_value = str(value).strip() if value is not None else "(empty)"
        items.append(_build_prose_sentence(str(key), str_value))

    if len(items) == 1:
        return f"The workflow completed successfully. Your {items[0]}."
    elif len(items) == 2:
        return f"The workflow completed successfully. Your {items[0]}, and {items[1]}."
    else:
        # Oxford-comma list for 3+
        joined = ", ".join(items[:-1]) + f", and {items[-1]}"
        return f"The workflow completed successfully. Your {joined}."


def format_error(exc_message: str | None) -> str:
    """
    Convert a raw exception message into a clean, user-friendly error string
    that Claude can relay conversationally.

    The returned string ALWAYS starts with ``_ERROR_SENTINEL`` so that
    ``DryRunHarness`` can detect error returns via a simple prefix check.

    Error categories (v2.4.2)
    --------------------------
    Known Playwright/network exception patterns are classified into one of
    five categories, each with a distinct, actionable recovery hint:

    - ``timeout``          — page or element took too long.
    - ``selector_not_found`` — a UI element is missing (site layout changed).
    - ``navigation_failed``  — page load or URL navigation failed.
    - ``network_error``      — connectivity / TCP-level failure.
    - ``auth_error``         — authentication / permission denied.

    Unrecognised exceptions fall through to the existing generic path,
    preserving full backward compatibility.

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

        # v2.4.2 — try to classify the error into a known category first.
        # Classify against the *original* raw message (before prefix stripping)
        # so we have the most signal available.
        category_hint = _classify_error(raw)
        if category_hint:
            return f"{_ERROR_SENTINEL} right now. {category_hint}"

        # Generic fallback — unchanged from v1
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
