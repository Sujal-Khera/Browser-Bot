"""
browserbot/agents/code_generator/coordinator.py — Step 5.3 Retry Coordinator.

Orchestrates the bounded code generation retry feedback loop. Coordinates:
Generator -> Validator -> Correction -> Generator (retry) -> Validator -> Success/Fail.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.agents.validator.pipeline import ValidationPipeline
from browserbot.logging import get_logger
from browserbot.models.correction_payload import CorrectionPayload
from browserbot.models.validation_report import ValidationReport
from browserbot.models.workflow_spec import WorkflowSpec
from browserbot.models.stage_event import StageEvent

log = get_logger(__name__)

MAX_RETRIES = 2


class PipelineCoordinator:
    """Orchestrates code generation, validation, and bounded retry feedback loops."""

    def __init__(
        self,
        generator: CodeGenerator,
        pipeline: ValidationPipeline,
        output_dir: Path,
        on_stage_event: Callable[[StageEvent], None] | None = None,
    ) -> None:
        self.generator = generator
        self.pipeline = pipeline
        self.output_dir = Path(output_dir).resolve()
        self.on_stage_event = on_stage_event

    def run(self, spec: WorkflowSpec, secret_overrides: dict[str, str] | None = None) -> ValidationReport:
        """
        Runs the generation and validation loop. Retries up to MAX_RETRIES times.

        Args:
            spec: The target WorkflowSpec.

        Returns:
            The final ValidationReport (successful or permanent failure).
        """
        correction: CorrectionPayload | None = None
        server_path = self.output_dir / "server.py"
        manifest_path = self.output_dir / "mcp_tool.json"
        report_path = self.output_dir / "validation_report.json"

        for attempt in range(MAX_RETRIES + 1):
            log.info(
                "Pipeline iteration started",
                extra={"attempt": attempt, "max_retries": MAX_RETRIES},
            )

            # 1. Generate code (with correction if attempt > 0)
            try:
                generated_code = self.generator.generate(spec, correction=correction)
            except Exception as exc:
                log.error("Generator failed during code generation", extra={"error": str(exc)})
                # Build an artificial validation report to reflect generator failure
                from browserbot.models.validation_report import StageResult
                dummy_stage = StageResult(success=False, message=str(exc))
                return ValidationReport(
                    generated_at=datetime.now(timezone.utc).isoformat(),
                    tool_dir=str(self.output_dir),
                    overall_success=False,
                    file_existence=dummy_stage,
                    compilation=dummy_stage,
                    import_check=dummy_stage,
                    runtime_dry_run=dummy_stage,
                )

            # Write generated code
            self.output_dir.mkdir(parents=True, exist_ok=True)
            server_path.write_text(generated_code, encoding="utf-8")
            log.info("Server script written", extra={"path": str(server_path)})

            # 2. Write tool manifest
            from browserbot.agents.code_generator.manifest import generate_manifest
            try:
                manifest = generate_manifest(spec)
                manifest.to_file(manifest_path)
            except Exception as exc:
                log.error("Failed to compile or write manifest", extra={"error": str(exc)})

            # 3. Validate
            report = self.pipeline.validate(spec, self.output_dir, secret_overrides=secret_overrides, on_stage_event=self.on_stage_event)
            report.to_file(report_path)

            # 4. Check success
            if report.overall_success:
                log.info(
                    "Pipeline execution succeeded",
                    extra={"attempt": attempt, "duration": report.runtime_dry_run.details.get("duration_seconds")}
                )
                return report

            # 5. Bounded retry check
            if attempt >= MAX_RETRIES:
                log.error(
                    "Pipeline failed permanently after maximum retries",
                    extra={"retries": attempt},
                )
                return report

            # 6. Build correction payload
            correction = self._build_correction(report, server_path)
            log.info(
                "Feedback correction payload compiled",
                extra={
                    "stage": correction.validation_stage,
                    "category": correction.error_category,
                    "summary": correction.validation_summary,
                },
            )

        # Fallback return
        return report

    def _build_correction(self, report: ValidationReport, server_path: Path) -> CorrectionPayload:
        """Constructs a minimal CorrectionPayload from a failed ValidationReport."""
        # Find which stage failed
        failed_stage = "runtime_dry_run"
        stage_res = report.runtime_dry_run

        if not report.file_existence.success:
            failed_stage = "file_existence"
            stage_res = report.file_existence
        elif not report.compilation.success:
            failed_stage = "compilation"
            stage_res = report.compilation
        elif not report.import_check.success:
            failed_stage = "import_check"
            stage_res = report.import_check

        exception_str = stage_res.details.get("error") or stage_res.details.get("exception") or stage_res.message
        
        # Categorise error
        if "syntax" in exception_str.lower() or failed_stage == "compilation":
            category = "SyntaxError"
        elif "import" in exception_str.lower() or failed_stage == "import_check":
            category = "ImportError"
        else:
            category = "RuntimeError"

        # Try to extract failing snippet
        snippet = self._extract_snippet(server_path, exception_str)

        return CorrectionPayload(
            validation_stage=failed_stage,
            failing_file=server_path.name,
            error_category=category,
            exception=exception_str,
            validation_summary=stage_res.message,
            relevant_code_snippet=snippet,
        )

    def _extract_snippet(self, server_path: Path, exception_text: str) -> str | None:
        """Extracts the relevant generated code block or the lines around the failing line."""
        try:
            code = server_path.read_text(encoding="utf-8")
        except Exception:
            return None

        # Look for a line number in the exception/traceback text
        # E.g. 'line 55', 'server.py", line 55'
        line_match = re.search(r"line\s+(\d+)", exception_text, re.IGNORECASE)
        if not line_match:
            # Also try matching server.py line layout
            line_match = re.search(r"server\.py.*?line\s+(\d+)", exception_text, re.IGNORECASE)

        lines = code.splitlines()

        if line_match:
            try:
                line_idx = int(line_match.group(1)) - 1  # 0-indexed
                # Capture 5 lines before and after the failure line
                start = max(0, line_idx - 5)
                end = min(len(lines), line_idx + 6)
                snippet_lines = []
                for i in range(start, end):
                    marker = ">>> " if i == line_idx else "    "
                    snippet_lines.append(f"{i + 1:3d}:{marker}{lines[i]}")
                return "\n".join(snippet_lines)
            except Exception:
                pass

        # Fallback: Extract only the workflow body section
        # (This keeps the context minimal as required, excluding the template headers/footers)
        body_lines = []
        in_body = False
        for i, line in enumerate(lines):
            if "---- WORKFLOW BODY START ----" in line:
                in_body = True
                continue
            if "---- WORKFLOW BODY END ----" in line:
                in_body = False
                break
            if in_body:
                body_lines.append(f"{i + 1:3d}:    {line}")

        if body_lines:
            return "\n".join(body_lines)

        return None
