"""
tests/test_registry.py — Phase 6.3: Claude Desktop Registration tests.

Run:
    python -m pytest tests/test_registry.py -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from browserbot.models.package import BrowserBotPackage, ClaudeConfigSnippet, PackageMetadata
from browserbot.runtime.registry import ClaudeDesktopRegistry, RegistrationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_package(tool_name: str = "execute_test_site", server_path: str = "/fake/server.py") -> BrowserBotPackage:
    """Build a minimal BrowserBotPackage fixture."""
    return BrowserBotPackage(
        package_version="1.0",
        package_name=tool_name,
        entry_point="server.py",
        dependencies=["fastmcp>=3.0.0", "playwright>=1.40.0"],
        claude_config_snippet=ClaudeConfigSnippet(
            command="python",
            args=[server_path],
            env={"BROWSERBOT_HEADLESS": "true"},
        ),
        metadata=PackageMetadata(
            browserbot_version="0.1.0",
            generated_at="2026-07-17T00:00:00Z",
            source_session_id="session_test",
            site="test.site",
        ),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_register_creates_config_when_absent(tmp_path: Path) -> None:
    """register() should create a new config file from scratch if none exists."""
    config_path = tmp_path / "claude_desktop_config.json"
    assert not config_path.exists()

    registry = ClaudeDesktopRegistry(config_path=config_path)
    pkg = _make_package()
    result = registry.register(pkg)

    assert config_path.exists()
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "execute_test_site" in data["mcpServers"]
    assert data["mcpServers"]["execute_test_site"]["command"] == "python"


def test_register_merges_with_existing_servers(tmp_path: Path) -> None:
    """register() must not destroy existing mcpServer entries."""
    config_path = tmp_path / "claude_desktop_config.json"
    # Pre-populate with another tool
    config_path.write_text(
        json.dumps({"mcpServers": {"some_other_tool": {"command": "node", "args": []}}}),
        encoding="utf-8",
    )

    registry = ClaudeDesktopRegistry(config_path=config_path)
    registry.register(_make_package("execute_new_tool"))

    data = json.loads(config_path.read_text(encoding="utf-8"))
    # Both tools must be present
    assert "some_other_tool" in data["mcpServers"]
    assert "execute_new_tool" in data["mcpServers"]


def test_register_overwrites_existing_entry(tmp_path: Path) -> None:
    """Registering a tool that already exists should overwrite that entry only."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"execute_test_site": {"command": "old", "args": []}}}),
        encoding="utf-8",
    )

    registry = ClaudeDesktopRegistry(config_path=config_path)
    registry.register(_make_package("execute_test_site", server_path="/new/server.py"))

    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["mcpServers"]["execute_test_site"]["command"] == "python"
    assert data["mcpServers"]["execute_test_site"]["args"] == ["/new/server.py"]


def test_register_dry_run_does_not_write(tmp_path: Path) -> None:
    """dry_run=True must not write the config file."""
    config_path = tmp_path / "claude_desktop_config.json"
    registry = ClaudeDesktopRegistry(config_path=config_path)
    registry.register(_make_package(), dry_run=True)
    assert not config_path.exists()


def test_register_backs_up_existing_config(tmp_path: Path) -> None:
    """register() must create a timestamped backup of the existing config."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    registry = ClaudeDesktopRegistry(config_path=config_path)
    registry.register(_make_package())

    backup_files = list(tmp_path.glob("*.bak.json"))
    assert len(backup_files) == 1, "Expected exactly one backup file"


def test_unregister_removes_tool(tmp_path: Path) -> None:
    """unregister() should remove an existing tool entry."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"execute_test_site": {"command": "python", "args": []}}}),
        encoding="utf-8",
    )

    registry = ClaudeDesktopRegistry(config_path=config_path)
    removed = registry.unregister("execute_test_site")

    assert removed is True
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "execute_test_site" not in data["mcpServers"]


def test_unregister_returns_false_when_not_found(tmp_path: Path) -> None:
    """unregister() should return False if the tool wasn't registered."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    registry = ClaudeDesktopRegistry(config_path=config_path)
    assert registry.unregister("nonexistent_tool") is False


def test_list_registered_returns_tool_names(tmp_path: Path) -> None:
    """list_registered() should return all mcpServers key names."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"tool_a": {}, "tool_b": {}}}),
        encoding="utf-8",
    )
    registry = ClaudeDesktopRegistry(config_path=config_path)
    names = registry.list_registered()
    assert set(names) == {"tool_a", "tool_b"}


def test_list_registered_empty_when_no_config(tmp_path: Path) -> None:
    """list_registered() returns [] when no config file exists."""
    config_path = tmp_path / "missing.json"
    registry = ClaudeDesktopRegistry(config_path=config_path)
    assert registry.list_registered() == []


def test_is_registered_true_and_false(tmp_path: Path) -> None:
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"my_tool": {}}}), encoding="utf-8"
    )
    registry = ClaudeDesktopRegistry(config_path=config_path)
    assert registry.is_registered("my_tool") is True
    assert registry.is_registered("other_tool") is False


def test_register_raises_on_invalid_json_config(tmp_path: Path) -> None:
    """register() should raise RegistrationError if the config file is corrupt."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text("NOT VALID JSON", encoding="utf-8")

    registry = ClaudeDesktopRegistry(config_path=config_path)
    with pytest.raises(RegistrationError, match="not valid JSON"):
        registry.register(_make_package())
