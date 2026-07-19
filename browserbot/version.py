"""
browserbot/version.py — Phase v2.6 Package Management & Versioning.

Provides version parsing, compatibility checks, and structured upgrade status
reporting for BrowserBot packages and installations.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from browserbot import __version__
from browserbot.logging import get_logger

log = get_logger(__name__)


class CompatibilityStatus(str, Enum):
    """Classification of package generator version relative to installed BrowserBot."""

    COMPATIBLE = "compatible"
    STALE = "stale"
    NEWER_GENERATOR = "newer_generator"
    INCOMPATIBLE = "incompatible"


class SemanticVersion(BaseModel):
    """Semantic version parser and comparator."""

    model_config = {"extra": "forbid"}

    raw: str
    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    @classmethod
    def parse(cls, version_str: str) -> SemanticVersion:
        """Parse a version string (e.g. '0.1.0', '1.2.3-dev', 'v2.0.0') into SemanticVersion."""
        cleaned = version_str.strip().lstrip("v")
        # Match major.minor.patch[-prerelease]
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.\-_]+))?$", cleaned)
        if not match:
            # Fallback for simple major.minor
            simple_match = re.match(r"^(\d+)\.(\d+)(?:-([a-zA-Z0-9.\-_]+))?$", cleaned)
            if simple_match:
                return cls(
                    raw=version_str,
                    major=int(simple_match.group(1)),
                    minor=int(simple_match.group(2)),
                    patch=0,
                    prerelease=simple_match.group(3),
                )
            raise ValueError(f"Invalid semantic version string: {version_str!r}")

        return cls(
            raw=version_str,
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
            prerelease=match.group(4),
        )

    def _tuple(self) -> tuple[int, int, int, int]:
        # Pre-releases compare lower than final releases of same number
        pre_val = 0 if self.prerelease is None else -1
        return (self.major, self.minor, self.patch, pre_val)

    def __lt__(self, other: SemanticVersion) -> bool:
        return self._tuple() < other._tuple()

    def __le__(self, other: SemanticVersion) -> bool:
        return self._tuple() <= other._tuple()

    def __gt__(self, other: SemanticVersion) -> bool:
        return self._tuple() > other._tuple()

    def __ge__(self, other: SemanticVersion) -> bool:
        return self._tuple() >= other._tuple()

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return False
        return self._tuple() == other._tuple()


class UpgradeStatus(BaseModel):
    """Structured report on package version compatibility and upgrade availability."""

    model_config = {"extra": "forbid"}

    installed_version: str
    generator_version: str
    status: CompatibilityStatus
    is_compatible: bool
    upgrade_available: bool
    upgrade_recommended: bool
    warning_message: str | None = None
    recommendation: str | None = None


def check_version_compatibility(
    generator_version: str,
    installed_version: str | None = None,
) -> UpgradeStatus:
    """
    Compare a package's generator_version against installed BrowserBot version.

    Args:
        generator_version: Version string stamped in package metadata.
        installed_version: Running BrowserBot version (defaults to browserbot.__version__).

    Returns:
        Structured UpgradeStatus object detailing compatibility and recommendations.
    """
    installed_str = installed_version or __version__

    try:
        gen_ver = SemanticVersion.parse(generator_version)
        inst_ver = SemanticVersion.parse(installed_str)
    except ValueError as err:
        log.warning("Version parsing failed", extra={"error": str(err)})
        return UpgradeStatus(
            installed_version=installed_str,
            generator_version=generator_version,
            status=CompatibilityStatus.INCOMPATIBLE,
            is_compatible=False,
            upgrade_available=True,
            upgrade_recommended=True,
            warning_message=f"Invalid or unparseable version string: {err}",
            recommendation="Re-generate the package with the current BrowserBot installation.",
        )

    # 1. Exact version match
    if gen_ver == inst_ver:
        return UpgradeStatus(
            installed_version=installed_str,
            generator_version=generator_version,
            status=CompatibilityStatus.COMPATIBLE,
            is_compatible=True,
            upgrade_available=False,
            upgrade_recommended=False,
            warning_message=None,
            recommendation=None,
        )

    # 2. Major version mismatch -> Incompatible
    if gen_ver.major != inst_ver.major:
        return UpgradeStatus(
            installed_version=installed_str,
            generator_version=generator_version,
            status=CompatibilityStatus.INCOMPATIBLE,
            is_compatible=False,
            upgrade_available=True,
            upgrade_recommended=True,
            warning_message=(
                f"Major version mismatch: package was generated with v{generator_version}, "
                f"but installed BrowserBot is v{installed_str}."
            ),
            recommendation="Re-record or re-generate the package to ensure compatibility.",
        )

    # 3. Older generator version -> Stale (Compatible, but Upgrade Recommended)
    if gen_ver < inst_ver:
        return UpgradeStatus(
            installed_version=installed_str,
            generator_version=generator_version,
            status=CompatibilityStatus.STALE,
            is_compatible=True,
            upgrade_available=True,
            upgrade_recommended=True,
            warning_message=(
                f"Package generator version (v{generator_version}) is older than "
                f"installed BrowserBot (v{installed_str})."
            ),
            recommendation="Re-generating the package is recommended to benefit from new runtime optimizations.",
        )

    # 4. Newer generator version -> Incompatible/Newer Generator
    return UpgradeStatus(
        installed_version=installed_str,
        generator_version=generator_version,
        status=CompatibilityStatus.NEWER_GENERATOR,
        is_compatible=False,
        upgrade_available=True,
        upgrade_recommended=True,
        warning_message=(
            f"Package generator version (v{generator_version}) is newer than "
            f"installed BrowserBot (v{installed_str})."
        ),
        recommendation=f"Upgrade your BrowserBot installation to v{generator_version} or higher.",
    )


def detect_package_upgrade(package_dir: str | Path) -> UpgradeStatus:
    """
    Inspect a package directory on disk and evaluate its upgrade status.

    Args:
        package_dir: Absolute or relative path to a generated package directory.

    Returns:
        Structured UpgradeStatus object.
    """
    path = Path(package_dir).resolve()
    manifest_path = path / "browserbot_package.json"

    if not manifest_path.exists():
        return UpgradeStatus(
            installed_version=__version__,
            generator_version="unknown",
            status=CompatibilityStatus.INCOMPATIBLE,
            is_compatible=False,
            upgrade_available=True,
            upgrade_recommended=True,
            warning_message=f"Missing browserbot_package.json in package directory: {path}",
            recommendation="Re-package the tool using BrowserBot.",
        )

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        gen_ver = data.get("metadata", {}).get("browserbot_version", "0.0.0")
        return check_version_compatibility(gen_ver)
    except Exception as exc:
        log.error("Failed to parse package manifest for upgrade detection", extra={"error": str(exc)})
        return UpgradeStatus(
            installed_version=__version__,
            generator_version="unknown",
            status=CompatibilityStatus.INCOMPATIBLE,
            is_compatible=False,
            upgrade_available=True,
            upgrade_recommended=True,
            warning_message=f"Corrupt or invalid package manifest: {exc}",
            recommendation="Re-package the tool using BrowserBot.",
        )
