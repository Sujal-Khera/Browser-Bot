"""
browserbot.runtime — runtime executor and Claude Desktop integration (Phase 6).

Houses:
  - ClaudeDesktopRegistry  (Step 6.3): register/unregister tools in Claude Desktop
  - result_formatter       (Step 6.4): convert tool output to human-readable prose
  - hello_tool             (Step 1.4): minimal smoke-test MCP server

Invoked by Claude Desktop via the MCP protocol.
"""

from browserbot.runtime.registry import ClaudeDesktopRegistry, RegistrationError
from browserbot.runtime.result_formatter import format_error, format_success
from browserbot.runtime.resilience import resolve_locator

__all__ = [
    "ClaudeDesktopRegistry",
    "RegistrationError",
    "format_success",
    "format_error",
    "resolve_locator",
]
