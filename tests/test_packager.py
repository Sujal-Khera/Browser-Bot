"""
tests/test_packager.py — Phase 6: Package generator and installation verification tests.

Runs offline.

Run:
    python -m pytest tests/test_packager.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from browserbot.agents.packager.packager import Packager, PackagingError
from browserbot.models.package import BrowserBotPackage


def _create_mock_tool_dir(tmp_path: Path, success: bool = True) -> Path:
    """Helper to mock a validated tool directory."""
    tool_dir = tmp_path / "mock_tool"
    tool_dir.mkdir()

    # 1. Create server.py
    (tool_dir / "server.py").write_text("# Mock Server code", encoding="utf-8")

    # 2. Create mcp_tool.json
    manifest_data = {
        "schema_version": "1.0",
        "mcp_tool_name": "execute_mock_site",
        "description": "Executes mock task",
        "parameters_schema": {
            "type": "object",
            "properties": {},
            "required": []
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-16T12:00:00Z",
            "source_session_id": "session_12345",
            "site": "mock.site"
        }
    }
    (tool_dir / "mcp_tool.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    # 3. Create validation_report.json
    report_data = {
        "schema_version": "1.0",
        "generated_at": "2026-07-16T12:00:00Z",
        "tool_dir": str(tool_dir),
        "overall_success": success,
        "file_existence": {"success": True, "message": "OK"},
        "compilation": {"success": True, "message": "OK"},
        "import_check": {"success": True, "message": "OK"},
        "runtime_dry_run": {"success": success, "message": "OK" if success else "Runtime error"}
    }
    (tool_dir / "validation_report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    return tool_dir


def test_packager_success(tmp_path: Path) -> None:
    tool_dir = _create_mock_tool_dir(tmp_path, success=True)
    out_dir = tmp_path / "package_out"

    packager = Packager()
    pkg = packager.package(tool_dir, out_dir)

    assert pkg.package_name == "execute_mock_site"
    assert pkg.entry_point == "server.py"
    assert "fastmcp>=3.0.0" in pkg.dependencies

    # Assert files exist in destination
    assert (out_dir / "server.py").exists()
    assert (out_dir / "mcp_tool.json").exists()
    assert (out_dir / "browserbot_package.json").exists()
    assert (out_dir / "install.ps1").exists()
    assert (out_dir / "requirements.txt").exists()
    assert (out_dir / "README.md").exists()

    # Validate generated package schema
    pkg_manifest = BrowserBotPackage.from_file(out_dir / "browserbot_package.json")
    assert pkg_manifest.package_name == "execute_mock_site"


def test_packager_fails_on_missing_report(tmp_path: Path) -> None:
    tool_dir = tmp_path / "empty_tool"
    tool_dir.mkdir()
    out_dir = tmp_path / "package_out"

    packager = Packager()
    with pytest.raises(PackagingError, match="Missing validation_report.json"):
        packager.package(tool_dir, out_dir)


def test_packager_fails_on_failed_validation(tmp_path: Path) -> None:
    tool_dir = _create_mock_tool_dir(tmp_path, success=False)
    out_dir = tmp_path / "package_out"

    packager = Packager()
    with pytest.raises(PackagingError, match="Cannot package tool. Validation failed"):
        packager.package(tool_dir, out_dir)


def test_verify_installation_success(tmp_path: Path) -> None:
    tool_dir = _create_mock_tool_dir(tmp_path, success=True)
    out_dir = tmp_path / "package_out"

    packager = Packager()
    packager.package(tool_dir, out_dir)

    assert packager.verify_installation(out_dir) is True


def test_verify_installation_missing_file(tmp_path: Path) -> None:
    tool_dir = _create_mock_tool_dir(tmp_path, success=True)
    out_dir = tmp_path / "package_out"

    packager = Packager()
    packager.package(tool_dir, out_dir)

    # Delete server.py to simulate broken integrity
    (out_dir / "server.py").unlink()

    assert packager.verify_installation(out_dir) is False


def test_verify_installation_mismatch_fails(tmp_path: Path) -> None:
    tool_dir = _create_mock_tool_dir(tmp_path, success=True)
    out_dir = tmp_path / "package_out"

    packager = Packager()
    packager.package(tool_dir, out_dir)

    # Mutate name in package manifest
    pkg_manifest_path = out_dir / "browserbot_package.json"
    data = json.loads(pkg_manifest_path.read_text(encoding="utf-8"))
    data["package_name"] = "mismatched_name"
    pkg_manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    assert packager.verify_installation(out_dir) is False
