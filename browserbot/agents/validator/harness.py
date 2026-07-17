"""
browserbot/agents/validator/harness.py — Step 5.1 Dry-Run Harness.

Dynamically imports the generated tool server, executes the workflow function
using parameter examples, and captures execution metrics (duration, stdout/stderr,
exceptions, failure screenshots).
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import io
import os
import sys
import time
from pathlib import Path
from typing import Any

from browserbot.logging import get_logger

log = get_logger(__name__)


class DryRunResult:
    """Encapsulates the raw execution result of a tool dry-run."""

    def __init__(
        self,
        success: bool,
        duration: float,
        output: str | None = None,
        stdout: str = "",
        stderr: str = "",
        exception: str | None = None,
        screenshot_path: Path | None = None,
    ) -> None:
        self.success = success
        self.duration = duration
        self.output = output
        self.stdout = stdout
        self.stderr = stderr
        self.exception = exception
        self.screenshot_path = screenshot_path


class DryRunHarness:
    """Harness to execute the generated MCP server code in an isolated dry-run."""

    def __init__(self, server_path: Path) -> None:
        self.server_path = server_path.resolve()

    def run(
        self,
        inputs: dict[str, str],
        screenshot_path: Path | None = None,
    ) -> DryRunResult:
        """
        Dynamically imports the server script, invokes run_workflow, and captures results.
        Runs synchronously by managing its own event loop or scheduling on the current loop.
        """
        log.info(
            "Starting dry-run harness",
            extra={"server_path": str(self.server_path), "inputs": list(inputs.keys())},
        )

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        
        # Configure env variables for screenshot on failure
        orig_ss_path = os.environ.get("BROWSERBOT_FAILURE_SCREENSHOT_PATH")
        if screenshot_path:
            os.environ["BROWSERBOT_FAILURE_SCREENSHOT_PATH"] = str(screenshot_path.resolve())
        else:
            os.environ.pop("BROWSERBOT_FAILURE_SCREENSHOT_PATH", None)

        start_time = time.perf_counter()
        success = False
        output_str = None
        captured_exception = None

        try:
            # 1. Dynamically import the module
            module_name = f"generated_tool_{int(start_time)}"
            spec = importlib.util.spec_from_file_location(module_name, str(self.server_path))
            if not spec or not spec.loader:
                raise ImportError(f"Could not load spec for {self.server_path}")

            module = importlib.util.module_from_spec(spec)
            
            # Redirect stdout/stderr during import and execution
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                spec.loader.exec_module(module)

                # 2. Extract tool function
                if not hasattr(module, "run_workflow"):
                    raise AttributeError("Generated module is missing 'run_workflow' entry point.")

                run_fn = getattr(module, "run_workflow")

                # 3. Execute the async function
                # Note: FastMCP run_workflow is async. Run it in a new event loop.
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    output_str = loop.run_until_complete(run_fn(**inputs))
                finally:
                    loop.close()

            # 4. Check return status
            # Step 6.4: tools now return human-readable prose, not JSON.
            # Success = non-empty string that does NOT start with the
            # _format_error sentinel phrase baked into the template.
            if output_str and output_str.strip():
                ERROR_SENTINEL = "I wasn't able to complete the workflow"
                if output_str.strip().startswith(ERROR_SENTINEL):
                    success = False
                    captured_exception = f"Workflow returned error: {output_str.strip()}"
                else:
                    success = True
            else:
                captured_exception = "Workflow returned no output."

        except Exception as exc:
            log.error("Exception during tool dry-run execution", extra={"error": str(exc)})
            captured_exception = f"{type(exc).__name__}: {str(exc)}"
            success = False

        finally:
            # Clean up env var
            if orig_ss_path is not None:
                os.environ["BROWSERBOT_FAILURE_SCREENSHOT_PATH"] = orig_ss_path
            else:
                os.environ.pop("BROWSERBOT_FAILURE_SCREENSHOT_PATH", None)

        duration = time.perf_counter() - start_time
        
        # Verify if screenshot was actually generated
        screenshot_exists = screenshot_path and screenshot_path.exists()
        actual_ss_path = screenshot_path if screenshot_exists else None

        log.info(
            "Dry-run harness complete",
            extra={
                "success": success,
                "duration": f"{duration:.2f}s",
                "screenshot_captured": screenshot_exists,
            },
        )

        return DryRunResult(
            success=success,
            duration=duration,
            output=output_str,
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            exception=captured_exception,
            screenshot_path=actual_ss_path,
        )
