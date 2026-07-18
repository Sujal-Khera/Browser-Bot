"""
browserbot.runtime — runtime executor and Claude Desktop integration (Phase 6).

Houses:
  - ClaudeDesktopRegistry  (Step 6.3): register/unregister tools in Claude Desktop
  - result_formatter       (Step 6.4): convert tool output to human-readable prose
  - hello_tool             (Step 1.4): minimal smoke-test MCP server

Invoked by Claude Desktop via the MCP protocol.
"""

from browserbot.runtime.registry import ClaudeDesktopRegistry, RegistrationError
from browserbot.runtime.result_formatter import format_success, format_error
from browserbot.runtime.resilience import resolve_locator, resilient_click, resilient_fill
from browserbot.runtime.pii_audit import audit_artifacts
from browserbot.runtime.benchmark import run_benchmark

__all__ = [
    "ClaudeDesktopRegistry",
    "RegistrationError",
    "format_success",
    "format_error",
    "resolve_locator",
    "resilient_click",
    "resilient_fill",
    "audit_artifacts",
    "run_benchmark",
]
