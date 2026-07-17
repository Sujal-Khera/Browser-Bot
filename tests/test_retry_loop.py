"""
tests/test_retry_loop.py — Step 5.3: Automated retry feedback loop tests.

Validates that validation failures trigger generator retries, that the
structured correction payload is correctly compiled and passed down to
the generator, that successful retries exit immediately, and that retry
decisions are bounded to exactly 2 retries.
Runs offline.

Run:
    python -m pytest tests/test_retry_loop.py -v
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from browserbot.agents.code_generator.coordinator import PipelineCoordinator
from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.agents.validator.pipeline import ValidationPipeline
from browserbot.models.correction_payload import CorrectionPayload
from browserbot.models.validation_report import StageResult, ValidationReport
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


def _build_dummy_report(
    success: bool,
    stage_fail: str = "runtime_dry_run",
    msg: str = "Success",
    exception: str = "",
) -> ValidationReport:
    """Helper to build a mock ValidationReport."""
    s_ok = StageResult(success=True, message="File exists")
    c_ok = StageResult(success=True, message="Compiled cleanly")
    i_ok = StageResult(success=True, message="Import successful")
    r_ok = StageResult(success=True, message="Dry-run passed")

    if not success:
        fail_stage = StageResult(
            success=False,
            message=msg,
            details={"error": exception, "exception": exception},
        )
        if stage_fail == "file_existence":
            s_ok = fail_stage
        elif stage_fail == "compilation":
            c_ok = fail_stage
        elif stage_fail == "import_check":
            i_ok = fail_stage
        else:
            r_ok = fail_stage

    return ValidationReport(
        generated_at="2026-07-16T12:00:00Z",
        tool_dir="dummy",
        overall_success=success,
        file_existence=s_ok,
        compilation=c_ok,
        import_check=i_ok,
        runtime_dry_run=r_ok,
    )


# ---------------------------------------------------------------------------
# Test 1: Validation succeeds on first try (no retries)
# ---------------------------------------------------------------------------


def test_coordinator_exits_immediately_on_success(tmp_path: Path) -> None:
    spec = _load_spec_from_session()
    
    # Mock generator to return code
    mock_gen = MagicMock(spec=CodeGenerator)
    mock_gen.generate.return_value = "# dummy code"
    
    # Mock validator pipeline to report success immediately
    mock_pipe = MagicMock(spec=ValidationPipeline)
    mock_pipe.validate.return_value = _build_dummy_report(success=True)

    coordinator = PipelineCoordinator(
        generator=mock_gen,
        pipeline=mock_pipe,
        output_dir=tmp_path,
    )

    report = coordinator.run(spec)

    assert report.overall_success is True
    # Generator called exactly once
    assert mock_gen.generate.call_count == 1
    mock_gen.generate.assert_has_calls([call(spec, correction=None)])


# ---------------------------------------------------------------------------
# Test 2: Validation fails once, retry succeeds (1 retry)
# ---------------------------------------------------------------------------


def test_coordinator_retries_and_succeeds(tmp_path: Path) -> None:
    spec = _load_spec_from_session()
    
    mock_gen = MagicMock(spec=CodeGenerator)
    # Returns code for both calls
    mock_gen.generate.side_effect = ["# bad code", "# corrected code"]
    
    mock_pipe = MagicMock(spec=ValidationPipeline)
    # 1st validate returns FAIL, 2nd validate returns PASS
    mock_pipe.validate.side_effect = [
        _build_dummy_report(
            success=False,
            stage_fail="compilation",
            msg="Compilation failed",
            exception="SyntaxError: invalid syntax at line 1",
        ),
        _build_dummy_report(success=True),
    ]

    coordinator = PipelineCoordinator(
        generator=mock_gen,
        pipeline=mock_pipe,
        output_dir=tmp_path,
    )

    # Mock the internal _extract_snippet to return a dummy snippet
    with patch.object(coordinator, "_extract_snippet", return_value="def run_workflow(:"):
        report = coordinator.run(spec)

    assert report.overall_success is True
    # Generator called exactly 2 times
    assert mock_gen.generate.call_count == 2
    
    # Assert that the second call received a CorrectionPayload
    args, kwargs = mock_gen.generate.call_args_list[1]
    correction = kwargs.get("correction")
    assert isinstance(correction, CorrectionPayload)
    assert correction.validation_stage == "compilation"
    assert correction.error_category == "SyntaxError"
    assert correction.validation_summary == "Compilation failed"
    assert correction.exception == "SyntaxError: invalid syntax at line 1"
    assert correction.relevant_code_snippet == "def run_workflow(:"


# ---------------------------------------------------------------------------
# Test 3: Bounded retry limit check (max 2 retries = 3 total attempts)
# ---------------------------------------------------------------------------


def test_coordinator_exhausts_retries_and_fails(tmp_path: Path) -> None:
    spec = _load_spec_from_session()
    
    mock_gen = MagicMock(spec=CodeGenerator)
    mock_gen.generate.return_value = "# always bad code"
    
    mock_pipe = MagicMock(spec=ValidationPipeline)
    # Always returns FAIL
    mock_pipe.validate.return_value = _build_dummy_report(
        success=False,
        stage_fail="runtime_dry_run",
        msg="Dry-run execution failed",
        exception="ValueError: Element not found on line 4",
    )

    coordinator = PipelineCoordinator(
        generator=mock_gen,
        pipeline=mock_pipe,
        output_dir=tmp_path,
    )

    report = coordinator.run(spec)

    assert report.overall_success is False
    # Max retries is 2. So 1 initial + 2 retries = 3 generator calls total
    assert mock_gen.generate.call_count == 3
    assert mock_pipe.validate.call_count == 3
