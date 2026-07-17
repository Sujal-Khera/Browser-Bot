"""
browserbot/runtime/registry.py — Step 6.3: Claude Desktop Registration Agent.

Reads the system Claude Desktop config file, merges the BrowserBot package
snippet into the mcpServers section, writes the result back, and prints a
clear confirmation.  Also supports dry-run (print-only) mode so developers
can review the change before it is written.

IMPORTANT
---------
This module makes a TARGETED, ADDITIVE edit to claude_desktop_config.json.
It never removes existing mcpServer entries.  If the tool name is already
registered it overwrites only that entry.

Config file locations
---------------------
- Windows : %APPDATA%\\Claude\\claude_desktop_config.json
- macOS   : ~/Library/Application Support/Claude/claude_desktop_config.json
- Linux   : ~/.config/Claude/claude_desktop_config.json  (unofficial)
"""

from __future__ import annotations

import json
import os
import platform
import shutil
from datetime import datetime, timezone
from pathlib import Path

from browserbot.logging import get_logger
from browserbot.models.package import BrowserBotPackage

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Config-file location resolution
# ---------------------------------------------------------------------------


def _claude_config_path() -> Path:
    """Return the platform-appropriate Claude Desktop config file path."""
    system = platform.system()
    if system == "Windows":
        # Check for Windows Store installation path redirection
        packages_dir = Path.home() / "AppData" / "Local" / "Packages"
        if packages_dir.exists():
            try:
                for folder in packages_dir.iterdir():
                    if folder.name.lower().startswith("claude_"):
                        store_path = folder / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
                        # If this store config directory exists, prioritize it
                        if store_path.parent.exists():
                            return store_path
            except Exception as exc:
                log.warning("Failed to iterate Windows packages dir", extra={"error": str(exc)})
        
        # Standard AppData fallback
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        # Linux / other — follow XDG convention
        xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(xdg) / "Claude" / "claude_desktop_config.json"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class RegistrationError(RuntimeError):
    """Raised when the registration cannot complete safely."""


class ClaudeDesktopRegistry:
    """
    Manages registration of BrowserBot-generated tools into Claude Desktop.

    Usage::

        registry = ClaudeDesktopRegistry()
        registry.register(package, dry_run=False)
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path: Path = config_path or _claude_config_path()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, package: BrowserBotPackage, *, dry_run: bool = False) -> dict:
        """
        Add (or update) the package entry in claude_desktop_config.json.

        Args:
            package: The compiled BrowserBotPackage to register.
            dry_run: If True, compute the new config but do NOT write it.

        Returns:
            The final config dict that would be / was written.
        """
        tool_name = package.package_name
        snippet = package.claude_config_snippet.model_dump(mode="json")

        # 1. Load existing config (or start from scratch)
        existing = self._load_config()
        if "mcpServers" not in existing:
            existing["mcpServers"] = {}

        # 2. Merge — additive, non-destructive
        already_registered = tool_name in existing["mcpServers"]
        existing["mcpServers"][tool_name] = snippet

        log.info(
            "Registration payload prepared",
            extra={
                "tool_name": tool_name,
                "already_registered": already_registered,
                "dry_run": dry_run,
                "config_path": str(self.config_path),
            },
        )

        if dry_run:
            print(
                f"\n[dry-run] The following entry would be written to:\n"
                f"  {self.config_path}\n\n"
                f"{json.dumps({'mcpServers': {tool_name: snippet}}, indent=2)}\n"
            )
            return existing

        # 3. Back up before write
        self._backup_config()

        # 4. Write
        self._write_config(existing)

        action = "updated" if already_registered else "registered"
        print(
            f"\n[BrowserBot] Tool '{tool_name}' {action} in Claude Desktop.\n"
            f"   Config: {self.config_path}\n"
            f"\n   Restart Claude Desktop for the change to take effect.\n"
        )
        return existing

    def unregister(self, tool_name: str, *, dry_run: bool = False) -> bool:
        """
        Remove a tool entry from claude_desktop_config.json.

        Args:
            tool_name: The mcp_tool_name / package_name to remove.
            dry_run:   If True, do not write changes.

        Returns:
            True if an entry was found and removed, False if it wasn't present.
        """
        existing = self._load_config()
        servers = existing.get("mcpServers", {})

        if tool_name not in servers:
            log.warning("Tool not found in Claude Desktop config — nothing to remove", extra={"tool_name": tool_name})
            return False

        del servers[tool_name]
        existing["mcpServers"] = servers

        if dry_run:
            print(f"\n[dry-run] Would remove '{tool_name}' from {self.config_path}")
            return True

        self._backup_config()
        self._write_config(existing)
        print(f"\n[BrowserBot] Tool '{tool_name}' removed from Claude Desktop config.\n")
        return True

    def list_registered(self) -> list[str]:
        """Return list of currently registered mcpServer keys."""
        config = self._load_config()
        return list(config.get("mcpServers", {}).keys())

    def is_registered(self, tool_name: str) -> bool:
        """Check whether a tool name is present in the Claude Desktop config."""
        return tool_name in self.list_registered()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_config(self) -> dict:
        """Load the Claude Desktop config JSON, returning {} if absent."""
        if not self.config_path.exists():
            log.info(
                "Claude Desktop config not found — will create a new one",
                extra={"config_path": str(self.config_path)},
            )
            return {}
        try:
            text = self.config_path.read_text(encoding="utf-8")
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RegistrationError(
                f"Claude Desktop config at {self.config_path} is not valid JSON: {exc}"
            ) from exc

    def _backup_config(self) -> Path | None:
        """Create a timestamped backup of the config before writing."""
        if not self.config_path.exists():
            return None
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = self.config_path.with_suffix(f".{ts}.bak.json")
        shutil.copy2(self.config_path, backup)
        log.info("Config backup created", extra={"backup": str(backup)})
        return backup

    def _write_config(self, config: dict) -> None:
        """Write the config dict to disk as pretty-printed JSON."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        log.info("Claude Desktop config written", extra={"path": str(self.config_path)})
