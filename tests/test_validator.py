"""
tests/test_validator.py — Step 5.1/5.2 automated unit tests.

Validates the dry-run harness, compilation check, import verification,
and error handling / screenshot stages in the ValidationPipeline.
Runs offline using standard unittest.mock patching.

Run:
    python -m pytest tests/test_validator.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from browserbot.agents.validator.harness import DryRunHarness, DryRunResult
from browserbot.agents.validator.pipeline import ValidationPipeline
from browserbot.models.validation_report import ValidationReport
from browserbot.models.workflow_spec import WorkflowSpec

FIXTURE_SINGLE = Path(__file__).parent / "fixtures" / "session_single_param.json"


def _load_spec_from_session() -> WorkflowSpec:
    """Helper to mock a WorkflowSpec directly from single parameter session fixture log."""
    from browserbot.models.action_log import ActionLog
    from browserbot.agents.pattern_extractor.generator import generate_workflow_spec
    from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput
    from browserbot.agents.pattern_extractor.models import ExtractedParameter
    
    log = ActionLog.from_file(FIXTURE_SINGLE)
    confirmed = ConfirmedOutput(
        parameters=[
            ExtractedParameter(
                name="search_query",
                example_value="learning agents",
                log_step_index=1,
                description="The search term to query",
                is_sensitive=False,
                is_optional=False,
            )
        ],
        fixed_step_indices=[0, 2],
        workflow_description="Search for a query on example.com",
    )
    return generate_workflow_spec(log, confirmed)


# ---------------------------------------------------------------------------
# Test 1: Validation succeeds under ideal conditions
# ---------------------------------------------------------------------------


def test_pipeline_overall_success(tmp_path: Path) -> None:
    # 1. Write dummy files that compile and import cleanly
    server_py = tmp_path / "server.py"
    server_py.write_text("def run_workflow(search_query):\n    return 'The workflow completed successfully.'\n", encoding="utf-8")
    
    mcp_tool_json = tmp_path / "mcp_tool.json"
    mcp_tool_json.write_text("{}", encoding="utf-8")

    spec = _load_spec_from_session()
    
    # Mock Harness to return success with prose output (Step 6.4)
    mock_result = DryRunResult(
        success=True,
        duration=1.2,
        output="The workflow completed successfully.",
        stdout="Hello stdout",
        stderr="Hello stderr",
    )
    
    with patch.object(DryRunHarness, "run", return_value=mock_result):
        pipeline = ValidationPipeline(screenshot_dir=tmp_path / "screenshots")
        report = pipeline.validate(spec, tmp_path)
        
    assert isinstance(report, ValidationReport)
    assert report.overall_success is True
    assert report.file_existence.success is True
    assert report.compilation.success is True
    assert report.import_check.success is True
    assert report.runtime_dry_run.success is True


# ---------------------------------------------------------------------------
# Test 2: Validation fails when files do not exist
# ---------------------------------------------------------------------------


def test_pipeline_fails_on_missing_files(tmp_path: Path) -> None:
    spec = _load_spec_from_session()
    pipeline = ValidationPipeline()
    report = pipeline.validate(spec, tmp_path)
    
    assert report.overall_success is False
    assert report.file_existence.success is False
    assert "Missing generated files" in report.file_existence.message
    # Subsequent stages should be skipped
    assert report.compilation.success is False
    assert "Skipped" in report.compilation.message


# ---------------------------------------------------------------------------
# Test 3: Validation fails on Python compilation syntax error
# ---------------------------------------------------------------------------


def test_pipeline_fails_on_compilation_error(tmp_path: Path) -> None:
    # Syntax error: missing parenthesis
    server_py = tmp_path / "server.py"
    server_py.write_text("def run_workflow(:\n   pass\n", encoding="utf-8")
    mcp_tool_json = tmp_path / "mcp_tool.json"
    mcp_tool_json.write_text("{}", encoding="utf-8")

    spec = _load_spec_from_session()
    pipeline = ValidationPipeline()
    report = pipeline.validate(spec, tmp_path)
    
    assert report.overall_success is False
    assert report.file_existence.success is True
    assert report.compilation.success is False
    assert "Compilation failed" in report.compilation.message
    assert report.import_check.success is False
    assert "Skipped" in report.import_check.message


# ---------------------------------------------------------------------------
# Test 4: Validation fails when import throws exception
# ---------------------------------------------------------------------------


def test_pipeline_fails_on_import_error(tmp_path: Path) -> None:
    # Compiles fine, but raises Exception during execution of import body
    server_py = tmp_path / "server.py"
    server_py.write_text("raise ValueError('Import failed!')\n", encoding="utf-8")
    mcp_tool_json = tmp_path / "mcp_tool.json"
    mcp_tool_json.write_text("{}", encoding="utf-8")

    spec = _load_spec_from_session()
    pipeline = ValidationPipeline()
    report = pipeline.validate(spec, tmp_path)
    
    assert report.overall_success is False
    assert report.file_existence.success is True
    assert report.compilation.success is True
    assert report.import_check.success is False
    assert "Import failed" in report.import_check.message
    assert report.runtime_dry_run.success is False


# ---------------------------------------------------------------------------
# Test 5: Validation fails when dry-run raises error or has bad status
# ---------------------------------------------------------------------------


def test_pipeline_fails_on_runtime_error(tmp_path: Path) -> None:
    server_py = tmp_path / "server.py"
    server_py.write_text("def run_workflow(search_query):\n    pass\n", encoding="utf-8")
    mcp_tool_json = tmp_path / "mcp_tool.json"
    mcp_tool_json.write_text("{}", encoding="utf-8")

    spec = _load_spec_from_session()
    
    # Mock Harness to return failure (e.g. status error or timeout exception)
    mock_result = DryRunResult(
        success=False,
        duration=0.5,
        exception="Playwright timeout waiting for selector",
        screenshot_path=tmp_path / "failure.png",
    )
    
    with patch.object(DryRunHarness, "run", return_value=mock_result):
        pipeline = ValidationPipeline()
        report = pipeline.validate(spec, tmp_path)
        
    assert report.overall_success is False
    assert report.runtime_dry_run.success is False
    assert "Dry-run execution failed" in report.runtime_dry_run.message
    assert report.runtime_dry_run.details["exception"] == "Playwright timeout waiting for selector"


# ---------------------------------------------------------------------------
# Test 6: Validation fails on missing expected outputs
# ---------------------------------------------------------------------------


def test_pipeline_fails_on_missing_outputs(tmp_path: Path) -> None:
    server_py = tmp_path / "server.py"
    server_py.write_text("def run_workflow(search_query):\n    pass\n", encoding="utf-8")
    mcp_tool_json = tmp_path / "mcp_tool.json"
    mcp_tool_json.write_text("{}", encoding="utf-8")

    # Force the spec to expect an output named 'results_count'
    spec = _load_spec_from_session()
    from browserbot.models import IROutput, SelectorInfo
    spec.outputs.append(
        IROutput(
            name="results_count",
            log_step_index=2,
            selector={"value": "div.count", "strategy": "css"},
            description="Number of results found",
        )
    )

    # Dry run succeeded, but its prose output does NOT mention 'Results Count'
    # (the human-readable form of 'results_count')
    mock_result = DryRunResult(
        success=True,
        duration=1.0,
        # prose that doesn't contain the expected label
        output="The workflow completed successfully.",
    )
    
    with patch.object(DryRunHarness, "run", return_value=mock_result):
        pipeline = ValidationPipeline()
        report = pipeline.validate(spec, tmp_path)
        
    assert report.overall_success is False
    assert report.runtime_dry_run.success is False
    # The pipeline should report the human-readable label as missing
    assert "Results Count" in report.runtime_dry_run.message
