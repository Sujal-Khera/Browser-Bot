"""
tests/test_observability.py — Phase 9A: Performance & Observability Unit Tests.

Validates the PII audit scans, timing measurements, and benchmarking modules.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from browserbot.runtime.pii_audit import audit_artifacts
from browserbot.runtime.benchmark import run_benchmark


def test_pii_audit_detects_literal_secrets(tmp_path: Path) -> None:
    """Verifies that the PII audit flags literal forbidden strings."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    
    server_file = package_dir / "server.py"
    server_file.write_text("password_val = 'super-secret-password'")

    violations = audit_artifacts(package_dir, forbidden_strings=["super-secret-password"])
    assert len(violations) > 0
    assert any("Found literal forbidden string placeholder" in v for v in violations)


def test_pii_audit_detects_suspicious_patterns(tmp_path: Path) -> None:
    """Verifies that the PII audit catches regex-based API key assignments."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    server_file = package_dir / "server.py"
    # Key assignment that should be caught
    server_file.write_text("my_api_key = \"abc123XYZ789foo_bar_token_value\"")

    violations = audit_artifacts(package_dir)
    assert len(violations) > 0
    assert any("Suspicious unredacted secret match" in v for v in violations)


def test_pii_audit_passes_redacted_safe_keys(tmp_path: Path) -> None:
    """Verifies that redacted placeholders do not trigger PII audit violations."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    server_file = package_dir / "server.py"
    server_file.write_text("password = '__SECRET_1__'")

    violations = audit_artifacts(package_dir)
    assert len(violations) == 0


@pytest.mark.asyncio
async def test_benchmark_runner_collects_metrics(tmp_path: Path) -> None:
    """Verifies that run_benchmark dynamically loads workflow modules, tracks runtimes, and writes reports."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()

    manifest_path = package_dir / "browserbot_package.json"
    # Build valid manifest
    manifest_content = {
        "package_version": "1.0",
        "package_name": "execute_test_benchmark",
        "entry_point": "server.py",
        "dependencies": [],
        "claude_config_snippet": {
            "command": "python",
            "args": ["server.py"],
            "env": {},
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-17T15:00:00Z",
            "source_session_id": "test_session",
            "site": "example.com",
        },
    }
    manifest_path.write_text(json.dumps(manifest_content))

    server_path = package_dir / "server.py"
    server_path.write_text("pass")

    # Mock the generated server.py module's async run_workflow function
    mock_run_workflow = AsyncMock(return_value="The workflow completed successfully.")
    
    mock_module = MagicMock()
    mock_module.run_workflow = mock_run_workflow

    with patch("importlib.util.spec_from_file_location") as mock_spec_loc, \
         patch("importlib.util.module_from_spec", return_value=mock_module):
        
        mock_loader = MagicMock()
        mock_spec = MagicMock()
        mock_spec.loader = mock_loader
        mock_spec_loc.return_value = mock_spec

        report = await run_benchmark(package_dir, iterations=2)
        
        assert report["overall_compliant"] is True
        assert report["metrics"]["runtime_runs"] == 2
        assert report["metrics"]["runtime_successes"] == 2
        
        assert (package_dir / "benchmark_report.json").exists()
        assert (package_dir / "benchmark_report.md").exists()
