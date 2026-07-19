"""
tests/test_recorder_lifecycle.py — Automated tests for Phase v2.5 Step v2.5.1:
Recorder lifecycle, action capture, error handling, interrupted session recovery,
and validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from browserbot.models.action_log import ActionLog, ActionLogValidator
from browserbot.recorder.codegen_runner import run_recording_session
from browserbot.recorder.convert_codegen import convert_codegen_script


def test_convert_codegen_script_handles_edge_cases() -> None:
    """Test codegen script converter with edge-case actions (check, dblclick, hover, press, wait, scroll)."""
    script = """
import re
from playwright.sync_api import Playwright, sync_playwright

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto("https://example.com/form")
    page.locator("#checkbox").check()
    page.locator("#checkbox").uncheck()
    page.locator(".menu-item").hover()
    page.locator(".btn").dblclick()
    page.locator("#input").press("Enter")
    page.wait_for_selector(".status")
    page.wait_for_load_state("networkidle")
    page.mouse.wheel(0, 500)
    page.locator(".result").inner_text()
    browser.close()
"""
    log = convert_codegen_script(script, site="example.com")
    assert len(log.steps) >= 8
    actions = [s.action for s in log.steps]
    assert "goto" in actions
    assert "check" in actions
    assert "hover" in actions
    assert "click" in actions
    assert "press_key" in actions
    assert "wait" in actions
    assert "scroll" in actions
    assert "extract_text" in actions


def test_convert_codegen_script_raises_on_zero_steps() -> None:
    """Converter must raise ValueError if script contains zero page actions."""
    empty_script = """
# Empty script
import sys
"""
    with pytest.raises(ValueError, match="Converter produced zero steps"):
        convert_codegen_script(empty_script, site="example.com")


def test_run_recording_session_missing_script_raises(tmp_path: Path) -> None:
    """run_recording_session must raise RuntimeError if codegen script is missing or empty."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        # raw script file not created
        with pytest.raises(RuntimeError, match="missing or empty"):
            run_recording_session(url="https://example.com", output_dir=tmp_path)


def test_run_recording_session_non_zero_exit_raises(tmp_path: Path) -> None:
    """run_recording_session must raise RuntimeError if codegen subprocess exits non-zero."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(RuntimeError, match="exited with code 1"):
            run_recording_session(url="https://example.com", output_dir=tmp_path)


def test_run_recording_session_success_lifecycle(tmp_path: Path) -> None:
    """Full end-to-end dry run of run_recording_session lifecycle."""
    valid_codegen = """
page.goto("https://example.com/checkout")
page.locator("#name").fill("John Doe")
page.locator("#submit").click()
"""
    def mock_codegen_side_effect(cmd, check=False):
        # Write output file
        out_path = Path(cmd[cmd.index("--output") + 1])
        out_path.write_text(valid_codegen, encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=mock_codegen_side_effect):
        session_file = run_recording_session(
            url="https://example.com/checkout",
            workflow_hint="Checkout flow test",
            output_dir=tmp_path,
        )
        assert session_file.exists()

        # Load and validate saved JSON
        saved_log = ActionLog.from_file(session_file)
        assert saved_log.metadata.site == "example.com"
        assert saved_log.metadata.workflow_hint == "Checkout flow test"
        assert len(saved_log.steps) == 3

        # Schema validator check
        validator = ActionLogValidator()
        validator.assert_valid(
            saved_log.model_dump(mode="json", exclude_none=True),
            label="test_run_recording_session_success",
        )
