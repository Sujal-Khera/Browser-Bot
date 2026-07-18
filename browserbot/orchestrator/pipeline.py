"""
browserbot/orchestrator/pipeline.py — Phase 7: Pipeline Orchestrator.

Sequentially chains the entire BrowserBot automation pipeline from:
Raw Action Log -> Scrubber -> Extractor -> IR Spec -> Generator -> Validator -> Packager -> Registry.
Produces a detailed diagnostics JSON report on execution (success or failure).
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browserbot.agents.code_generator.coordinator import PipelineCoordinator
from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.agents.packager.packager import Packager
from browserbot.agents.pattern_extractor.confirmer import confirm_parameters, ConfirmedOutput
from browserbot.agents.pattern_extractor.extractor import PatternExtractor
from browserbot.agents.pattern_extractor.generator import generate_workflow_spec
from browserbot.agents.validator.pipeline import ValidationPipeline
from browserbot.logging import get_logger
from browserbot.models.action_log import ActionLog
from browserbot.models.package import BrowserBotPackage
from browserbot.models.validation_report import ValidationReport
from browserbot.models.workflow_spec import WorkflowSpec
from browserbot.recorder.scrubber import scrub
from browserbot.runtime.registry import ClaudeDesktopRegistry

log = get_logger(__name__)


class PipelineOrchestrationError(RuntimeError):
    """Raised when any step of the orchestration pipeline fails."""


class OrchestrationPipeline:
    """
    Coordinates end-to-end execution of the BrowserBot workflow pipeline.
    Useful for programmatic execution, integration tests, and UI backends.
    """

    def __init__(self, *, dry_run: bool = True, backend: str | None = None) -> None:
        self.dry_run = dry_run
        self.backend = backend

    def run(
        self,
        raw_action_log_path: Path | str,
        output_dir: Path | str,
        package_dir: Path | str,
        *,
        register: bool = False,
        param_overrides: dict[str, Any] | None = None,
        registry_config_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """
        Runs the full pipeline. Writes pipeline_diagnostics.json to output_dir.

        Args:
            raw_action_log_path: Path to the raw recorded session JSON.
            output_dir: Intermediate code generation/validation directory.
            package_dir: Destination packaging directory.
            register: Whether to register the compiled tool with Claude Desktop.
            param_overrides: Optional overrides for confirmed parameters.
            registry_config_path: Optional path override to Claude config file.

        Returns:
            A dictionary containing stage output models and status metrics.
        """
        raw_action_log_path = Path(raw_action_log_path).resolve()
        output_dir = Path(output_dir).resolve()
        package_dir = Path(package_dir).resolve()

        log.info(
            "Starting end-to-end pipeline execution",
            extra={
                "raw_log": str(raw_action_log_path),
                "output_dir": str(output_dir),
                "package_dir": str(package_dir),
                "dry_run": self.dry_run,
                "register": register,
            },
        )

        stages_status = {
            "stage_1_scrubbing": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
            "stage_2_pattern_extraction": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
            "stage_3_parameter_confirmation": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
            "stage_4_ir_generation": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
            "stage_5_codegen_validation": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
            "stage_6_packaging": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
            "stage_7_claude_registration": {"success": False, "message": "Pending", "error": None, "duration_seconds": None},
        }
        overall_success = False
        failure_reason = None
        total_start = time.perf_counter()

        # Return dict variables
        scrubbed_log = None
        extractor_output = None
        spec = None
        report = None
        package = None
        registered_config = None

        try:
            # ----------------------------------------------------
            # Stage 1: Load and Scrub raw action log
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            stages_status["stage_1_scrubbing"]["message"] = "In progress"
            if not raw_action_log_path.exists():
                raise FileNotFoundError(f"Action log file not found: {raw_action_log_path}")

            log.info("Loading action log")
            action_log = ActionLog.from_file(raw_action_log_path)
            log.info("Scrubbing action log for PII")
            scrub_result = scrub(action_log)
            scrubbed_log = scrub_result.action_log
            stages_status["stage_1_scrubbing"]["success"] = True
            stages_status["stage_1_scrubbing"]["message"] = "Scrub complete"
            stages_status["stage_1_scrubbing"]["duration_seconds"] = time.perf_counter() - t_stage

            # ----------------------------------------------------
            # Stage 2: Pattern Extraction
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            stages_status["stage_2_pattern_extraction"]["message"] = "In progress"
            log.info("Running pattern extractor agent")
            extractor = PatternExtractor(dry_run=self.dry_run, backend=self.backend)
            extractor_output = extractor.extract(scrubbed_log)
            stages_status["stage_2_pattern_extraction"]["success"] = True
            stages_status["stage_2_pattern_extraction"]["message"] = "Pattern extraction complete"
            stages_status["stage_2_pattern_extraction"]["duration_seconds"] = time.perf_counter() - t_stage

            # ----------------------------------------------------
            # Stage 3: Parameter Confirmation (auto-confirm mode)
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            stages_status["stage_3_parameter_confirmation"]["message"] = "In progress"
            log.info("Confirming parameters (auto-confirm mode)")
            confirmed_output = confirm_parameters(extractor_output, auto_confirm=True)
            
            # Apply programmatic overrides if provided (useful for tests/UI)
            if param_overrides:
                for param in confirmed_output.parameters:
                    if param.name in param_overrides:
                        for k, v in param_overrides[param.name].items():
                            setattr(param, k, v)
            stages_status["stage_3_parameter_confirmation"]["success"] = True
            stages_status["stage_3_parameter_confirmation"]["message"] = "Parameters confirmed"
            stages_status["stage_3_parameter_confirmation"]["duration_seconds"] = time.perf_counter() - t_stage

            # ----------------------------------------------------
            # Stage 4: Generate Workflow Spec IR
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            stages_status["stage_4_ir_generation"]["message"] = "In progress"
            log.info("Generating Intermediate Representation (IR) workflow spec")
            spec = generate_workflow_spec(scrubbed_log, confirmed_output)
            output_dir.mkdir(parents=True, exist_ok=True)
            spec_path = output_dir / "workflow_spec.json"
            spec.to_file(spec_path)
            stages_status["stage_4_ir_generation"]["success"] = True
            stages_status["stage_4_ir_generation"]["message"] = "IR Spec generated"
            stages_status["stage_4_ir_generation"]["duration_seconds"] = time.perf_counter() - t_stage

            # ----------------------------------------------------
            # Stage 5: Code Generation, Validation & Bounded Retries
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            stages_status["stage_5_codegen_validation"]["message"] = "In progress"
            log.info("Running code generation validator pipeline coordinator")
            generator = CodeGenerator(dry_run=self.dry_run, backend=self.backend)
            pipeline = ValidationPipeline()
            coordinator = PipelineCoordinator(
                generator=generator,
                pipeline=pipeline,
                output_dir=output_dir,
            )
            secret_overrides = {}
            session_id = scrubbed_log.metadata.session_id
            secrets_path = Path(raw_action_log_path).parent / f"{session_id}_secrets.json"
            if secrets_path.exists():
                try:
                    with open(secrets_path, "r", encoding="utf-8") as f:
                        secret_overrides = json.load(f)
                    log.info("Loaded secrets overrides from disk", extra={"path": str(secrets_path)})
                except Exception as exc:
                    log.warning("Failed to load secrets mapping from disk", extra={"path": str(secrets_path), "error": str(exc)})
            
            if not secret_overrides and scrub_result.value_map:
                secret_overrides = {
                    placeholder: plaintext
                    for plaintext, placeholder in scrub_result.value_map.items()
                }

            report = coordinator.run(spec, secret_overrides=secret_overrides)
            if not report.overall_success:
                raise RuntimeError("Validation report status is overall_success = False")
            stages_status["stage_5_codegen_validation"]["success"] = True
            stages_status["stage_5_codegen_validation"]["message"] = "Code compilation and validation passed"
            stages_status["stage_5_codegen_validation"]["duration_seconds"] = time.perf_counter() - t_stage

            # ----------------------------------------------------
            # Stage 6: Packaging & Installation verification
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            stages_status["stage_6_packaging"]["message"] = "In progress"
            log.info("Compiling installable package")
            packager = Packager()
            package = packager.package(output_dir, package_dir)
            verified = packager.verify_installation(package_dir)
            if not verified:
                raise RuntimeError("Installation integrity verification checks failed.")
            stages_status["stage_6_packaging"]["success"] = True
            stages_status["stage_6_packaging"]["message"] = "Package generated and verified successfully"
            stages_status["stage_6_packaging"]["duration_seconds"] = time.perf_counter() - t_stage

            # ----------------------------------------------------
            # Stage 7: Claude Desktop Registration (optional)
            # ----------------------------------------------------
            t_stage = time.perf_counter()
            if register:
                stages_status["stage_7_claude_registration"]["message"] = "In progress"
                log.info("Registering packaged tool with Claude Desktop")
                registry = ClaudeDesktopRegistry(config_path=Path(registry_config_path) if registry_config_path else None)
                registered_config = registry.register(package)
                stages_status["stage_7_claude_registration"]["success"] = True
                stages_status["stage_7_claude_registration"]["message"] = "Tool registered in Claude config"
                stages_status["stage_7_claude_registration"]["duration_seconds"] = time.perf_counter() - t_stage
            else:
                stages_status["stage_7_claude_registration"]["message"] = "Skipped"
                stages_status["stage_7_claude_registration"]["duration_seconds"] = 0.0

            overall_success = True
            log.info("End-to-end pipeline completed successfully")

        except PipelineOrchestrationError as exc:
            failure_reason = str(exc)
            log.error("Pipeline orchestration failed", extra={"error": failure_reason})
            for stage_name, status in stages_status.items():
                if status["message"] == "In progress":
                    status["success"] = False
                    status["message"] = "Failed during stage execution"
                    status["error"] = failure_reason
                    status["duration_seconds"] = time.perf_counter() - t_stage
                    break
            raise
        except Exception as exc:
            # Map exception details to current stage and throw orchestrator error
            failure_reason = str(exc)
            log.error("Pipeline orchestration failed", extra={"error": failure_reason})

            # Detect which stage was active when exception was thrown
            for stage_name, status in stages_status.items():
                if status["message"] == "In progress":
                    status["success"] = False
                    status["message"] = f"Failed during stage execution"
                    status["error"] = failure_reason
                    status["duration_seconds"] = time.perf_counter() - t_stage
                    break
            raise PipelineOrchestrationError(f"Stage execution failed: {exc}") from exc

        finally:
            # Always save diagnostics summary to disk for observability (Step 7.2)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
                diag_path = output_dir / "pipeline_diagnostics.json"
                diag_data = {
                    "pipeline_version": "0.1.0",
                    "execution_timestamp": datetime.now(timezone.utc).isoformat(),
                    "dry_run": self.dry_run,
                    "total_duration_seconds": time.perf_counter() - total_start,
                    "stages": stages_status,
                    "overall_success": overall_success,
                    "failure_reason": failure_reason,
                }
                diag_path.write_text(json.dumps(diag_data, indent=2), encoding="utf-8")
                log.info("Pipeline diagnostics report written to disk", extra={"path": str(diag_path)})
            except Exception as ss_exc:
                log.error("Failed to write diagnostics report", extra={"error": str(ss_exc)})

        return {
            "scrubbed_log": scrubbed_log,
            "extractor_output": extractor_output,
            "spec": spec,
            "validation_report": report,
            "package": package,
            "registered_config": registered_config,
        }
