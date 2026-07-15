"""
browserbot/runtime/hello_tool.py — Step 1.4: FastMCP "Hello Tool" scaffold.

PURPOSE
-------
This is the minimal FastMCP server that proves the MCP plumbing works
before any generation logic is involved.

It exposes exactly one hard-coded tool:

    hello_browserbot()  ->  "Hello from BrowserBot! The MCP plumbing works."

There is NO:
- recorder logic
- LLM logic
- code generation logic
- Playwright automation
- BrowserBot pipeline logic of any kind

This server is intentionally the simplest possible FastMCP server.
Its only job is to validate that FastMCP -> stdio -> Claude Desktop wiring
functions correctly before generated-code complexity is layered on top.

RUNNING
-------
Start the server (stdio transport, for Claude Desktop):

    python -m browserbot.runtime.hello_tool

Or directly:

    python browserbot/runtime/hello_tool.py

CLAUDE DESKTOP CONFIG
---------------------
Add to claude_desktop_config.json:

    {
      "mcpServers": {
        "browserbot-hello": {
          "command": "python",
          "args": ["-m", "browserbot.runtime.hello_tool"],
          "cwd": "/absolute/path/to/BrowserBot"
        }
      }
    }

Then ask Claude Desktop: "call the hello browserbot tool"

Expected response: "Hello from BrowserBot! The MCP plumbing works."

VERIFICATION (Step 1.4)
-----------------------
Test that the server can be imported and introspected without starting stdio:

    python -c "
    from browserbot.runtime.hello_tool import mcp
    tools = mcp._tool_manager.get_tools()
    print([t.name for t in tools.values()])
    "

Expected output: ['hello_browserbot']
"""

from __future__ import annotations

from fastmcp import FastMCP

from browserbot.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Server definition
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="BrowserBot Hello",
    instructions=(
        "This is the BrowserBot MCP scaffold. "
        "Call the hello_browserbot tool to verify that MCP plumbing is working."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Tool definition — one static tool, fixed return value, no parameters
# ---------------------------------------------------------------------------


@mcp.tool
def hello_browserbot() -> str:
    """
    Verify that the BrowserBot MCP server is reachable.

    Returns a fixed confirmation string.  No parameters, no side effects.
    This tool exists only to validate the FastMCP -> Claude Desktop wiring.
    """
    log.info("hello_browserbot tool invoked")
    return "Hello from BrowserBot! The MCP plumbing works."


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("Starting BrowserBot Hello Tool MCP server (stdio transport)")
    mcp.run()
