"""
tests/test_integration.py — Phase 7A: End-to-End Pipeline Integration Tests.

Validates that the entire BrowserBot pipeline functions deterministically and
successfully end-to-end:
Raw Action Log -> Scrubber -> Extractor -> IR Spec -> Generator -> Validator -> Packager -> Registry.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from browserbot.agents.validator.harness import DryRunHarness, DryRunResult
from browserbot.models.package import BrowserBotPackage
from browserbot.models.validation_report import ValidationReport
from browserbot.orchestrator.pipeline import OrchestrationPipeline, PipelineOrchestrationError
from browserbot.runtime.registry import ClaudeDesktopRegistry


FIXTURE_SINGLE = Path(__file__).parent / "fixtures" / "session_single_param.json"
FIXTURE_MULTI = Path(__file__).parent / "fixtures" / "session_multi_params.json"


def test_integration_pipeline_success_dry_run(tmp_path: Path) -> None:
    """
    Tests the complete end-to-end pipeline under dry-run conditions.
    Verifies data flows cleanly between scrubber, extractor, spec generator,
    Jinja2 generator, pipeline validator, package bundler, and registration.
    """
    output_dir = tmp_path / "codegen_out"
    package_dir = tmp_path / "package_out"
    config_path = tmp_path / "claude_desktop_config.json"

    # Instantiate the end-to-end pipeline in dry-run mode
    pipeline = OrchestrationPipeline(dry_run=True)

    # Mock the DryRunHarness.run execution to simulate a successful Playwright run (Step 6.4 prose contract)
    mock_run_result = DryRunResult(
        success=True,
        duration=0.8,
        output="The workflow completed successfully.\n• Search Input: learning agents",
        stdout="Replay stdout",
        stderr="Replay stderr",
    )

    with patch.object(DryRunHarness, "run", return_value=mock_run_result):
        
        # Execute the pipeline
        results = pipeline.run(
            raw_action_log_path=FIXTURE_SINGLE,
            output_dir=output_dir,
            package_dir=package_dir,
            register=True,
            registry_config_path=config_path,
        )

    # ----------------------------------------------------
    # Assertions on pipeline outputs
    # ----------------------------------------------------
    
    # 1. Scrubber assertions
    assert results["scrubbed_log"] is not None
    assert results["scrubbed_log"].metadata.site == "example.com"

    # 2. Extractor assertions
    assert results["extractor_output"] is not None
    assert len(results["extractor_output"].parameters) == 1
    # Check the parameter mapping format
    assert results["extractor_output"].parameters[0].name == "search_input"

    # 3. Intermediate Representation (spec) assertions
    assert results["spec"] is not None
    assert isinstance(results["spec"], type(results["spec"]))
    assert results["spec"].workflow.site == "example.com"
    assert (output_dir / "workflow_spec.json").exists()

    # 4. Code Generation & Validation Pipeline assertions
    assert results["validation_report"] is not None
    assert isinstance(results["validation_report"], ValidationReport)
    assert results["validation_report"].overall_success is True
    assert (output_dir / "server.py").exists()
    assert (output_dir / "mcp_tool.json").exists()

    # 5. Packager assertions
    assert results["package"] is not None
    assert isinstance(results["package"], BrowserBotPackage)
    assert results["package"].package_name == "execute_example_com"
    assert (package_dir / "browserbot_package.json").exists()
    assert (package_dir / "server.py").exists()
    assert (package_dir / "mcp_tool.json").exists()
    assert (package_dir / "install.ps1").exists()
    assert (package_dir / "requirements.txt").exists()

    # 6. Registry assertions
    assert results["registered_config"] is not None
    assert config_path.exists()
    
    config_data = json.loads(config_path.read_text(encoding="utf-8"))
    assert "mcpServers" in config_data
    assert "execute_example_com" in config_data["mcpServers"]
    
    snippet = config_data["mcpServers"]["execute_example_com"]
    assert Path(snippet["command"]).stem in ("python", "pythonw")
    assert snippet["args"] == [str(package_dir / "server.py")]


def test_integration_pipeline_handles_zero_params(tmp_path: Path) -> None:
    """
    Tests the complete end-to-end pipeline with zero parameters.
    Verifies validation and server generation succeed when no inputs are dynamic.
    """
    raw_log_path = tmp_path / "session_zero.json"
    
    # Write a zero-parameter action log
    zero_log = {
        "schema_version": "1.0",
        "metadata": {
            "session_id": "session_zero_20260716T120000",
            "site": "static.com",
            "start_url": "https://static.com",
            "recorded_at": "2026-07-16T12:00:00Z",
            "browserbot_version": "0.1.0",
            "duration_seconds": 1.0,
            "step_count": 1,
            "workflow_hint": "Static navigation"
        },
        "steps": [
            {
                "step_index": 0,
                "action": "goto",
                "timestamp_offset": 0.0,
                "url": "https://static.com",
                "wait_until": "networkidle"
            }
        ]
    }
    raw_log_path.write_text(json.dumps(zero_log), encoding="utf-8")

    output_dir = tmp_path / "codegen_out"
    package_dir = tmp_path / "package_out"

    pipeline = OrchestrationPipeline(dry_run=True)

    # Dry-run harness success response (no outputs extracted)
    mock_run_result = DryRunResult(
        success=True,
        duration=0.5,
        output="The workflow completed successfully. No data was extracted.",
        stdout="stdout",
        stderr="stderr",
    )

    with patch.object(DryRunHarness, "run", return_value=mock_run_result):
        results = pipeline.run(
            raw_action_log_path=raw_log_path,
            output_dir=output_dir,
            package_dir=package_dir,
            register=False,
        )

    assert results["extractor_output"].parameters == []
    assert results["validation_report"].overall_success is True
    assert results["package"].package_name == "execute_static_com"


def test_integration_pipeline_raises_on_validation_failure(tmp_path: Path) -> None:
    """
    Tests that the pipeline correctly raises PipelineOrchestrationError and propagates
    the failure when validation fails after all retries are exhausted.
    """
    output_dir = tmp_path / "codegen_out"
    package_dir = tmp_path / "package_out"

    pipeline = OrchestrationPipeline(dry_run=True)

    # Mock the DryRunHarness to raise a compiler or runtime failure
    mock_fail_result = DryRunResult(
        success=False,
        duration=0.4,
        exception="Playwright timeout: selector '#not-found' not visible",
        stdout="",
        stderr="",
    )

    with patch.object(DryRunHarness, "run", return_value=mock_fail_result):
        with pytest.raises(PipelineOrchestrationError, match="Validation report status is overall_success = False"):
            pipeline.run(
                raw_action_log_path=FIXTURE_SINGLE,
                output_dir=output_dir,
                package_dir=package_dir,
                register=False,
            )

    # Ensure intermediate artifacts generated up to the failure are still written for diagnostics
    assert (output_dir / "workflow_spec.json").exists()
    assert (output_dir / "server.py").exists()
    assert (output_dir / "validation_report.json").exists()
    # But it must not package or copy files to the final destination
    assert not (package_dir / "browserbot_package.json").exists()
    
    # Assert that diagnostics were successfully written on failure
    diag_path = output_dir / "pipeline_diagnostics.json"
    assert diag_path.exists()
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    assert diag["overall_success"] is False
    assert "Validation report status is overall_success = False" in diag["failure_reason"]
    assert diag["stages"]["stage_5_codegen_validation"]["success"] is False
    assert "Validation report status is overall_success = False" in diag["stages"]["stage_5_codegen_validation"]["error"]


def test_integration_pipeline_saves_diagnostics_on_success(tmp_path: Path) -> None:
    """Verifies that the diagnostics JSON is properly compiled and saved on success."""
    output_dir = tmp_path / "codegen_out"
    package_dir = tmp_path / "package_out"

    pipeline = OrchestrationPipeline(dry_run=True)
    mock_run_result = DryRunResult(
        success=True,
        duration=0.5,
        output="The workflow completed successfully.\n• Search Input: query",
    )

    with patch.object(DryRunHarness, "run", return_value=mock_run_result):
        pipeline.run(
            raw_action_log_path=FIXTURE_SINGLE,
            output_dir=output_dir,
            package_dir=package_dir,
            register=False,
        )

    diag_path = output_dir / "pipeline_diagnostics.json"
    assert diag_path.exists()
    
    diag = json.loads(diag_path.read_text(encoding="utf-8"))
    assert diag["overall_success"] is True
    assert diag["failure_reason"] is None
    assert diag["stages"]["stage_1_scrubbing"]["success"] is True
    assert diag["stages"]["stage_6_packaging"]["success"] is True


def test_integration_pipeline_is_deterministic(tmp_path: Path) -> None:
    """Runs the pipeline multiple times and asserts output files are 100% identical."""
    mock_run_result = DryRunResult(
        success=True,
        duration=0.3,
        output="The workflow completed successfully.\n• Search Input: test",
    )

    outputs = []
    packages = []

    with patch.object(DryRunHarness, "run", return_value=mock_run_result):
        for i in range(3):
            out_dir = tmp_path / f"codegen_out_{i}"
            pkg_dir = tmp_path / f"package_out_{i}"
            
            pipeline = OrchestrationPipeline(dry_run=True)
            pipeline.run(
                raw_action_log_path=FIXTURE_SINGLE,
                output_dir=out_dir,
                package_dir=pkg_dir,
                register=False,
            )

            # Load compiled server.py and package manifest content
            server_code = (pkg_dir / "server.py").read_text(encoding="utf-8")
            manifest_text = (pkg_dir / "browserbot_package.json").read_text(encoding="utf-8")
            
            outputs.append(server_code)
            
            # Remove timestamp and dynamic config paths to match schemas exactly
            manifest_data = json.loads(manifest_text)
            manifest_data["metadata"].pop("generated_at", None)
            
            # Mask the target server path in args since it is directory-specific
            if "claude_config_snippet" in manifest_data and "args" in manifest_data["claude_config_snippet"]:
                manifest_data["claude_config_snippet"]["args"] = ["<masked_server_py_path>"]
                
            packages.append(manifest_data)

    # Assert outputs are identical across repeated executions
    assert outputs[0] == outputs[1] == outputs[2]
    assert packages[0] == packages[1] == packages[2]

