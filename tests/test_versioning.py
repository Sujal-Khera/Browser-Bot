"""
tests/test_versioning.py — Phase v2.6 Package Versioning & Upgrade Detection Tests.

Verifies version parsing, compatibility matrix, upgrade detection, and doctor integration.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from browserbot.version import (
    CompatibilityStatus,
    SemanticVersion,
    UpgradeStatus,
    check_version_compatibility,
    detect_package_upgrade,
)
from browserbot.cli.doctor import DoctorReport, check_package_versions


def test_semantic_version_parsing() -> None:
    """Verifies that version strings parse correctly into major, minor, patch, prerelease."""
    v1 = SemanticVersion.parse("0.1.0")
    assert v1.major == 0
    assert v1.minor == 1
    assert v1.patch == 0
    assert v1.prerelease is None

    v2 = SemanticVersion.parse("1.2.3-dev")
    assert v2.major == 1
    assert v2.minor == 2
    assert v2.patch == 3
    assert v2.prerelease == "dev"

    v3 = SemanticVersion.parse("v2.5.1")
    assert v3.major == 2
    assert v3.minor == 5
    assert v3.patch == 1

    with pytest.raises(ValueError):
        SemanticVersion.parse("invalid_ver_string")


def test_semantic_version_comparison() -> None:
    """Verifies semantic version comparison operators (<, <=, >, >=, ==)."""
    v0_1_0 = SemanticVersion.parse("0.1.0")
    v0_1_1 = SemanticVersion.parse("0.1.1")
    v0_2_0 = SemanticVersion.parse("0.2.0")
    v1_0_0 = SemanticVersion.parse("1.0.0")

    assert v0_1_0 < v0_1_1
    assert v0_1_1 < v0_2_0
    assert v0_2_0 < v1_0_0
    assert v0_1_0 == SemanticVersion.parse("0.1.0")
    assert v1_0_0 > v0_1_0


def test_compatibility_matching_versions() -> None:
    """Verifies that matching generator and installed versions report COMPATIBLE."""
    status = check_version_compatibility(generator_version="0.1.0", installed_version="0.1.0")
    assert status.status == CompatibilityStatus.COMPATIBLE
    assert status.is_compatible is True
    assert status.upgrade_available is False
    assert status.upgrade_recommended is False
    assert status.warning_message is None


def test_compatibility_older_generator_version() -> None:
    """Verifies that older generator versions report STALE with recommendations."""
    status = check_version_compatibility(generator_version="0.1.0", installed_version="0.2.0")
    assert status.status == CompatibilityStatus.STALE
    assert status.is_compatible is True
    assert status.upgrade_available is True
    assert status.upgrade_recommended is True
    assert "older than" in status.warning_message.lower()
    assert "re-generating" in status.recommendation.lower()


def test_compatibility_newer_generator_version() -> None:
    """Verifies that newer generator versions report NEWER_GENERATOR and incompatible."""
    status = check_version_compatibility(generator_version="0.3.0", installed_version="0.2.0")
    assert status.status == CompatibilityStatus.NEWER_GENERATOR
    assert status.is_compatible is False
    assert status.upgrade_available is True
    assert status.upgrade_recommended is True
    assert "newer than" in status.warning_message.lower()
    assert "upgrade your browserbot installation" in status.recommendation.lower()


def test_compatibility_major_mismatch() -> None:
    """Verifies that major version mismatches report INCOMPATIBLE."""
    status = check_version_compatibility(generator_version="1.0.0", installed_version="0.2.0")
    assert status.status == CompatibilityStatus.INCOMPATIBLE
    assert status.is_compatible is False
    assert status.upgrade_available is True
    assert status.upgrade_recommended is True
    assert "major version mismatch" in status.warning_message.lower()


def test_compatibility_invalid_version_string() -> None:
    """Verifies graceful handling of invalid version strings."""
    status = check_version_compatibility(generator_version="not-a-version", installed_version="0.1.0")
    assert status.status == CompatibilityStatus.INCOMPATIBLE
    assert status.is_compatible is False
    assert "invalid" in status.warning_message.lower()


def test_detect_package_upgrade_from_disk(tmp_path: Path) -> None:
    """Verifies reading a package directory on disk and detecting upgrade status."""
    pkg_dir = tmp_path / "packages" / "execute_test_site"
    pkg_dir.mkdir(parents=True)
    
    manifest_data = {
        "package_version": "1.0",
        "package_name": "execute_test_site",
        "entry_point": "server.py",
        "dependencies": ["fastmcp>=3.0.0"],
        "claude_config_snippet": {
            "command": "python",
            "args": ["server.py"],
            "env": {}
        },
        "metadata": {
            "browserbot_version": "0.1.0-dev",
            "generated_at": "2026-07-19T12:00:00Z",
            "source_session_id": "session_123",
            "site": "test.com"
        }
    }
    (pkg_dir / "browserbot_package.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    status = detect_package_upgrade(pkg_dir)
    assert isinstance(status, UpgradeStatus)
    assert status.generator_version == "0.1.0-dev"
    assert status.installed_version is not None


def test_detect_package_upgrade_missing_manifest(tmp_path: Path) -> None:
    """Verifies detection handling when browserbot_package.json is missing."""
    empty_dir = tmp_path / "empty_pkg"
    empty_dir.mkdir()

    status = detect_package_upgrade(empty_dir)
    assert status.status == CompatibilityStatus.INCOMPATIBLE
    assert status.is_compatible is False
    assert "missing" in status.warning_message.lower()


def test_doctor_package_version_check(tmp_path: Path) -> None:
    """Verifies Doctor command integrates package version diagnostics."""
    packages_dir = tmp_path / "packages"
    pkg_dir = packages_dir / "execute_demo"
    pkg_dir.mkdir(parents=True)
    manifest = {
        "package_version": "1.0",
        "package_name": "execute_demo",
        "entry_point": "server.py",
        "dependencies": [],
        "claude_config_snippet": {"command": "python", "args": ["server.py"], "env": {}},
        "metadata": {"browserbot_version": "0.0.1", "generated_at": "2026-01-01T00:00:00Z", "source_session_id": "s1", "site": "demo.com"}
    }
    (pkg_dir / "browserbot_package.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = DoctorReport()
    check_package_versions(report, quiet=True, packages_dir=packages_dir)

    assert len(report.checks) == 1
    assert report.checks[0].status == "WARN"
    assert "stale" in report.checks[0].message.lower()
