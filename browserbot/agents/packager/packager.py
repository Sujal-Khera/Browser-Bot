"""
browserbot/agents/packager/packager.py — Phase 6: Package Generator & Verification agent.

Generates the final installable tool package directory structure, manifest,
and verification logic.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browserbot import __version__
from browserbot.logging import get_logger
from browserbot.models.mcp_tool import MCPToolManifest
from browserbot.models.package import BrowserBotPackage, ClaudeConfigSnippet, PackageMetadata
from browserbot.models.validation_report import ValidationReport

log = get_logger(__name__)


class PackagingError(ValueError):
    """Raised when packaging requirements or validation assertions fail."""


class Packager:
    """Handles deterministic packaging and installation verification for generated MCP servers."""

    def __init__(self) -> None:
        pass

    def package(self, tool_dir: Path, output_dir: Path) -> BrowserBotPackage:
        """
        Takes a validated tool directory, packages it into output_dir.

        Args:
            tool_dir: Path to directory containing validated tool files.
            output_dir: Path to destination package folder.

        Returns:
            The compiled BrowserBotPackage manifest instance.
        """
        tool_dir = Path(tool_dir).resolve()
        output_dir = Path(output_dir).resolve()
        
        log.info(
            "Starting package compilation",
            extra={"tool_dir": str(tool_dir), "output_dir": str(output_dir)},
        )

        # 1. Assert validation success
        report_path = tool_dir / "validation_report.json"
        if not report_path.exists():
            raise PackagingError(f"Missing validation_report.json in {tool_dir}. Run validation first.")
        
        report = ValidationReport.from_file(report_path)
        if not report.overall_success:
            raise PackagingError(
                f"Cannot package tool. Validation failed on stage: "
                f"{report.runtime_dry_run.message if not report.runtime_dry_run.success else 'unknown'}"
            )

        # 2. Read tool manifest for metadata
        manifest_path = tool_dir / "mcp_tool.json"
        if not manifest_path.exists():
            raise PackagingError(f"Missing mcp_tool.json manifest in {tool_dir}.")
        
        manifest = MCPToolManifest.from_file(manifest_path)

        # 3. Create target directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # 4. Copy required files
        shutil.copy2(tool_dir / "server.py", output_dir / "server.py")
        shutil.copy2(manifest_path, output_dir / "mcp_tool.json")
        shutil.copy2(report_path, output_dir / "validation_report.json")

        # 5. Build Claude configuration snippet
        target_server = output_dir / "server.py"
        snippet = ClaudeConfigSnippet(
            command=sys.executable,
            args=[str(target_server)],
            env={"BROWSERBOT_HEADLESS": "true"},
        )

        # 6. Build package metadata
        metadata = PackageMetadata(
            browserbot_version=__version__,
            generated_at=datetime.now(timezone.utc).isoformat(),
            source_session_id=manifest.metadata.source_session_id,
            site=manifest.metadata.site,
        )

        # 7. Compile manifest
        pkg = BrowserBotPackage(
            package_version="1.0",
            package_name=manifest.mcp_tool_name,
            entry_point="server.py",
            dependencies=["fastmcp>=3.0.0", "playwright>=1.40.0"],
            claude_config_snippet=snippet,
            metadata=metadata,
        )

        # Save package manifest
        pkg_manifest_path = output_dir / "browserbot_package.json"
        pkg.to_file(pkg_manifest_path)

        # 8. Generate installation script files
        self._generate_install_files(output_dir, pkg)

        log.info(
            "Packaging completed successfully",
            extra={"package_name": pkg.package_name, "manifest": str(pkg_manifest_path)},
        )
        return pkg

    def verify_installation(self, package_dir: Path) -> bool:
        """
        Step 6.2 Installation verification. Checks structure, integrity, and config integration.

        Args:
            package_dir: Path to directory of the generated package.

        Returns:
            True if installation structure is validated successfully.
        """
        package_dir = Path(package_dir).resolve()
        log.info("Verifying installation structure", extra={"package_dir": str(package_dir)})

        # 1. Required files existence check
        req_files = ["server.py", "mcp_tool.json", "browserbot_package.json", "install.ps1", "requirements.txt"]
        for name in req_files:
            file_path = package_dir / name
            if not file_path.exists():
                log.error("Installation verification failed: missing file", extra={"file": name})
                return False

        # 2. Manifest Schema validation
        try:
            pkg = BrowserBotPackage.from_file(package_dir / "browserbot_package.json")
            manifest = MCPToolManifest.from_file(package_dir / "mcp_tool.json")
        except Exception as exc:
            log.error("Installation verification failed: schema error", extra={"error": str(exc)})
            return False

        # 3. Integrity and Casing match checks
        if pkg.package_name != manifest.mcp_tool_name:
            log.error(
                "Installation verification failed: package name mismatch",
                extra={"package": pkg.package_name, "manifest": manifest.mcp_tool_name},
            )
            return False

        # 4. Dependency consistency check
        deps_txt = (package_dir / "requirements.txt").read_text(encoding="utf-8")
        for dep in pkg.dependencies:
            # Check if each package dependency is present in requirements.txt (basic match)
            base_name = dep.split(">")[0].split("=")[0].strip()
            if base_name not in deps_txt:
                log.error("Installation verification failed: dependency missing in requirements.txt", extra={"dependency": base_name})
                return False

        # 5. Simulate installing into a clean Claude Desktop Configuration
        clean_claude_config = {"mcpServers": {}}
        try:
            snippet = pkg.claude_config_snippet.model_dump(mode="json")
            # Inject snippet
            clean_claude_config["mcpServers"][pkg.package_name] = snippet
            # Ensure JSON serialization works
            config_str = json.dumps(clean_claude_config)
            loaded = json.loads(config_str)
            # Verify integration content
            injected_mcp = loaded["mcpServers"][pkg.package_name]
            assert Path(injected_mcp["command"]).stem in ("python", "pythonw")
            assert len(injected_mcp["args"]) == 1
            assert Path(injected_mcp["args"][0]).name == "server.py"
        except Exception as exc:
            log.error("Installation verification failed: Claude configuration simulation error", extra={"error": str(exc)})
            return False

        log.info("Installation verification passed successfully", extra={"package_dir": str(package_dir)})
        return True

    def _generate_install_files(self, output_dir: Path, pkg: BrowserBotPackage) -> None:
        """Helper to create install script and requirements files."""
        # 1. requirements.txt
        reqs = [f"{dep}\n" for dep in pkg.dependencies]
        (output_dir / "requirements.txt").write_text("".join(reqs), encoding="utf-8")

        # 2. install.ps1 Powershell installation guidance
        snippet_json = json.dumps(
            {
                "mcpServers": {
                    pkg.package_name: pkg.claude_config_snippet.model_dump(mode="json")
                }
            },
            indent=2,
        )

        ps_content = f"""# BrowserBot Stdio Tool Installation Script for {pkg.package_name}
# Run this script to view the configuration block for Claude Desktop.

$configSnippet = @'
{snippet_json}
'@

$claudeConfigDir = "$env:APPDATA\\Claude"
$claudeConfigFile = "$claudeConfigDir\\claude_desktop_config.json"

Write-Host "============================================================"
Write-Host "Installing BrowserBot Stdio Tool: {pkg.package_name}"
Write-Host "============================================================"
Write-Host ""
Write-Host "To install manually, add the following snippet to your Claude config:"
Write-Host "Location: $claudeConfigFile"
Write-Host ""
Write-Host $configSnippet
Write-Host ""

# Create Claude config directory if missing
if (-not (Test-Path $claudeConfigDir)) {{
    New-Item -ItemType Directory -Path $claudeConfigDir | Out-Null
}}

Write-Host "Installation files prepared successfully."
"""
        (output_dir / "install.ps1").write_text(ps_content, encoding="utf-8")
