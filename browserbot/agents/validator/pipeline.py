"""
browserbot/agents/validator/pipeline.py — Step 5.2 Verification Pipeline.

Orchestrates all validation stages (File Existence, Compilation, Import Check,
Runtime Dry-Run, and Output Schema verification), generating a structured
ValidationReport.
"""

from __future__ import annotations

import importlib.util
import py_compile
import sys
from datetime import datetime, timezone
from pathlib import Path

from browserbot.agents.validator.harness import DryRunHarness
from browserbot.logging import get_logger
from browserbot.models.validation_report import StageResult, ValidationReport
from browserbot.models.workflow_spec import WorkflowSpec

log = get_logger(__name__)


class ValidationPipeline:
    """Orchestrates structured validation stages on generated tools."""

    def __init__(self, screenshot_dir: Path | None = None) -> None:
        self.screenshot_dir = screenshot_dir or Path("screenshots")

    def validate(self, spec: WorkflowSpec, tool_dir: Path, secret_overrides: dict[str, str] | None = None) -> ValidationReport:
        """
        Executes all validation stages on the generated tool directory.

        Args:
            spec: The WorkflowSpec IR used to generate the tool.
            tool_dir: The directory where the server.py and mcp_tool.json are located.

        Returns:
            A ValidationReport object detailing stage statuses.
        """
        tool_dir = Path(tool_dir).resolve()
        server_py = tool_dir / "server.py"
        mcp_tool_json = tool_dir / "mcp_tool.json"
        
        log.info("Starting validation pipeline", extra={"tool_dir": str(tool_dir)})

        # ---------------------------------------------------------
        # Stage 1: File Existence
        # ---------------------------------------------------------
        exists_server = server_py.exists()
        exists_manifest = mcp_tool_json.exists()
        
        file_exist_ok = exists_server and exists_manifest
        file_exist_msg = "All generated files exist." if file_exist_ok else "Missing generated files."
        file_exist_details = {
            "server_py_exists": exists_server,
            "mcp_tool_json_exists": exists_manifest,
        }
        stage_file_existence = StageResult(
            success=file_exist_ok,
            message=file_exist_msg,
            details=file_exist_details,
        )

        # ---------------------------------------------------------
        # Stage 2: Compilation
        # ---------------------------------------------------------
        compile_ok = False
        compile_msg = "Skipped (preceding step failed)"
        compile_details = {}

        if file_exist_ok:
            try:
                py_compile.compile(str(server_py), doraise=True)
                compile_ok = True
                compile_msg = "Python compilation successful."
            except py_compile.PyCompileError as exc:
                compile_ok = False
                compile_msg = f"Compilation failed: {exc.msg}"
                compile_details = {"error": str(exc)}
            except Exception as exc:
                compile_ok = False
                compile_msg = f"Unexpected compilation error: {exc}"
                compile_details = {"error": str(exc)}

        stage_compilation = StageResult(
            success=compile_ok,
            message=compile_msg,
            details=compile_details,
        )

        # ---------------------------------------------------------
        # Stage 3: Import Check
        # ---------------------------------------------------------
        import_ok = False
        import_msg = "Skipped (preceding step failed)"
        import_details = {}

        if compile_ok:
            try:
                mod_spec = importlib.util.spec_from_file_location("test_import", str(server_py))
                if mod_spec and mod_spec.loader:
                    mod = importlib.util.module_from_spec(mod_spec)
                    mod_spec.loader.exec_module(mod)
                    import_ok = True
                    import_msg = "Generated module imported successfully."
                else:
                    import_msg = "Import spec could not be created."
            except Exception as exc:
                import_ok = False
                import_msg = f"Import failed: {type(exc).__name__}: {str(exc)}"
                import_details = {"error": str(exc)}

        stage_import_check = StageResult(
            success=import_ok,
            message=import_msg,
            details=import_details,
        )

        # ---------------------------------------------------------
        # Stage 4 & 5: Runtime Dry-Run & Expected Output Check
        # ---------------------------------------------------------
        runtime_ok = False
        runtime_msg = "Skipped (preceding step failed)"
        runtime_details = {}

        if import_ok:
            # Prepare inputs from spec defaults
            inputs = {p.name: p.example_value for p in spec.parameters}
            if secret_overrides:
                for k, v in inputs.items():
                    if isinstance(v, str) and v in secret_overrides:
                        inputs[k] = secret_overrides[v]
            
            # Setup failure screenshot path
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            ss_path = self.screenshot_dir / f"failure_{spec.workflow.site}_{timestamp}.png"

            harness = DryRunHarness(server_py)
            res = harness.run(inputs, screenshot_path=ss_path)

            runtime_details = {
                "duration_seconds": res.duration,
                "stdout": res.stdout,
                "stderr": res.stderr,
                "exception": res.exception,
            }

            if res.success:
                # Stage 5 — output validation (Step 6.4: tools return prose, not JSON)
                # The harness already confirmed no error sentinel.
                # Here we verify the prose output is non-empty and meaningful,
                # and that if the spec defines expected output keys, the prose
                # mentions at least one of them (best-effort).
                output_text = (res.output or "").strip()
                if not output_text:
                    runtime_ok = False
                    runtime_msg = "Dry-run returned an empty response."
                    runtime_details["empty_output"] = True
                else:
                    expected_keys = {o.name for o in spec.outputs}
                    # Convert snake_case output names to human-readable form for
                    # matching against the prose (e.g. "order_status" → "Order Status")
                    human_keys = {k.replace("_", " ").title() for k in expected_keys}
                    missing_keys = {
                        k for k in human_keys
                        if k.lower() not in output_text.lower()
                    }
                    if expected_keys and missing_keys:
                        runtime_ok = False
                        runtime_msg = (
                            f"Dry-run succeeded but output prose does not mention "
                            f"expected outputs: {list(missing_keys)}"
                        )
                        runtime_details["missing_outputs"] = list(missing_keys)
                    else:
                        runtime_ok = True
                        runtime_msg = "Dry-run and outputs validation successful."
                        runtime_details["output_length"] = len(output_text)
            else:
                runtime_ok = False
                runtime_msg = f"Dry-run execution failed: {res.exception}"
                if res.screenshot_path:
                    runtime_details["screenshot_captured"] = str(res.screenshot_path)

        stage_runtime_dry_run = StageResult(
            success=runtime_ok,
            message=runtime_msg,
            details=runtime_details,
        )

        # Overall validation state
        overall_success = (
            stage_file_existence.success
            and stage_compilation.success
            and stage_import_check.success
            and stage_runtime_dry_run.success
        )

        report = ValidationReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            tool_dir=str(tool_dir),
            overall_success=overall_success,
            file_existence=stage_file_existence,
            compilation=stage_compilation,
            import_check=stage_import_check,
            runtime_dry_run=stage_runtime_dry_run,
        )

        log.info(
            "Validation pipeline complete",
            extra={"overall_success": overall_success, "tool_dir": str(tool_dir)},
        )
        return report
