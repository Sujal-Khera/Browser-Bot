"""
BrowserBot — local-first browser automation → MCP tool generator.

Record once.  Auto-generate a reusable MCP tool.  Invoke via Claude.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__: str = version("browserbot")
except PackageNotFoundError:
    __version__ = "0.1.0-dev"

__all__ = ["__version__"]
