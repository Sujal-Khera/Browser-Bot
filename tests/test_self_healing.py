"""
tests/test_self_healing.py — Phase 8B: Self-Healing and Timing Resilience Unit Tests.

Validates the resilient locator replay behaviors (retry-with-backoff) and the
automated package self-healing orchestration routines.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from browserbot.runtime.resilience import resilient_click, resilient_fill
from browserbot.orchestrator.self_healing import self_heal_package
from browserbot.orchestrator.pipeline import OrchestrationPipeline


def _build_valid_manifest(package_name: str, session_id: str) -> dict:
    """Builds a schema-valid package manifest dictionary for mock testing."""
    return {
        "package_version": "1.0",
        "package_name": package_name,
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
            "source_session_id": session_id,
            "site": "example.com",
        },
    }


@pytest.mark.asyncio
async def test_resilient_click_success_first_attempt() -> None:
    """Verifies that resilient_click executes successfully on the first attempt."""
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock()
    mock_locator.click = AsyncMock()

    with patch("browserbot.runtime.resilience.resolve_locator", return_value=mock_locator):
        await resilient_click(mock_page, {"value": "btn"})
        mock_locator.wait_for.assert_called_once_with(state="visible", timeout=1500)
        mock_locator.click.assert_called_once()


@pytest.mark.asyncio
async def test_resilient_click_retry_success() -> None:
    """Verifies that resilient_click retries with backoff and succeeds on subsequent tries."""
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock()
    
    # First click fails, second click succeeds
    mock_locator.click = AsyncMock(side_effect=[Exception("Transient error"), None])

    with patch("browserbot.runtime.resilience.resolve_locator", return_value=mock_locator), \
         patch("asyncio.sleep", AsyncMock()) as mock_sleep:
        
        await resilient_click(mock_page, {"value": "btn"})
        assert mock_locator.click.call_count == 2
        mock_sleep.assert_called_once_with(0.1)


@pytest.mark.asyncio
async def test_resilient_click_permanent_failure() -> None:
    """Verifies that resilient_click raises RuntimeError when all retries fail."""
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock()
    mock_locator.click = AsyncMock(side_effect=Exception("Permanent error"))

    with patch("browserbot.runtime.resilience.resolve_locator", return_value=mock_locator), \
         patch("asyncio.sleep", AsyncMock()):
        
        with pytest.raises(RuntimeError, match="Resilient click failed after 4 retries"):
            await resilient_click(mock_page, {"value": "btn"})


@pytest.mark.asyncio
async def test_resilient_fill_success() -> None:
    """Verifies resilient_fill happy path works on first attempt."""
    mock_page = MagicMock()
    mock_locator = MagicMock()
    mock_locator.wait_for = AsyncMock()
    mock_locator.fill = AsyncMock()

    with patch("browserbot.runtime.resilience.resolve_locator", return_value=mock_locator):
        await resilient_fill(mock_page, {"value": "input"}, "some text")
        mock_locator.wait_for.assert_called_once_with(state="visible", timeout=1500)
        mock_locator.fill.assert_called_once_with("some text", timeout=1500)


def test_self_heal_package_skipped_when_healthy(tmp_path: Path) -> None:
    """Verifies self-healing is skipped if needs_healing.flag is absent."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    manifest_path = package_dir / "browserbot_package.json"
    manifest_content = _build_valid_manifest("execute_test", "test_session_id")
    manifest_path.write_text(json.dumps(manifest_content))

    # Should skip since needs_healing.flag doesn't exist
    assert self_heal_package(package_dir, force=False) is False


def test_self_heal_package_raises_on_missing_session(tmp_path: Path) -> None:
    """Verifies self-healing raises FileNotFoundError if original session log cannot be located."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    manifest_path = package_dir / "browserbot_package.json"
    flag_path = package_dir / "needs_healing.flag"
    
    manifest_content = _build_valid_manifest("execute_test", "non_existent_session_id")
    manifest_path.write_text(json.dumps(manifest_content))
    flag_path.write_text("Playwright timeout")

    with pytest.raises(FileNotFoundError, match="Could not locate original action log"):
        self_heal_package(package_dir)


def test_self_heal_package_success(tmp_path: Path) -> None:
    """Verifies that self_heal_package re-runs the orchestration pipeline and deletes needs_healing.flag."""
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    manifest_path = package_dir / "browserbot_package.json"
    flag_path = package_dir / "needs_healing.flag"

    manifest_content = _build_valid_manifest("execute_test", "test_session_id")
    manifest_path.write_text(json.dumps(manifest_content))
    flag_path.write_text("Playwright timeout")

    # Create dummy session log so lookup succeeds
    session_dir = Path("workflows/sessions")
    session_dir.mkdir(parents=True, exist_ok=True)
    dummy_log = session_dir / "session_test_session_id.json"
    
    # We must match standard action log schema
    dummy_log_content = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": "test_session_id",
            "site": "example.com",
            "start_url": "https://example.com",
            "recorded_at": "2026-07-17T15:00:00Z",
            "browserbot_version": "0.1.0",
            "duration_seconds": 1.0,
            "step_count": 1
        },
        "steps": [
            {
                "step_index": 0,
                "action": "goto",
                "timestamp_offset": 0.0,
                "url": "https://example.com"
            }
        ]
    }
    dummy_log.write_text(json.dumps(dummy_log_content))

    # Mock the OrchestrationPipeline.run method to simulate success
    with patch.object(OrchestrationPipeline, "run", return_value={}) as mock_run:
        healed = self_heal_package(package_dir, registry_config_path=tmp_path / "claude_config.json")
        assert healed is True
        mock_run.assert_called_once()
        # The flag file should have been deleted on successful heal
        assert not flag_path.exists()

    # Clean up dummy log file
    if dummy_log.exists():
        dummy_log.unlink()
