"""
browserbot/agents/code_generator/__main__.py — Step 4.2 CLI entry point.

Usage:
    # Dry-run generation (deterministic translation)
    python -m browserbot.agents.code_generator --input workflow_spec.json --output generated_tools/check_order_status/

    # Real LLM generation (using Qwen/Ollama by default)
    python -m browserbot.agents.code_generator --input workflow_spec.json --output generated_tools/check_order_status/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.logging import get_logger
from browserbot.models.workflow_spec import WorkflowSpec

log = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m browserbot.agents.code_generator",
        description="BrowserBot Phase 4 — Code Generator Engine",
    )
    p.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to the confirmed workflow_spec.json Intermediate Representation file.",
    )
    p.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the output directory or file where the generated server.py will be written.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip the LLM call and generate Playwright steps deterministically from the spec.",
    )
    p.add_argument(
        "--backend",
        choices=["ollama", "groq"],
        default=None,
        help="LLM backend to use. Defaults to settings.llm_backend (ollama).",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override the model name (e.g. 'qwen2.5-coder:7b'). Sets OLLAMA_MODEL_GENERATOR.",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Maximum number of LLM retries on DSL validation failure.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    spec_path: Path = args.input
    if not spec_path.exists():
        print(f"[error] Spec file not found: {spec_path}", file=sys.stderr)
        return 1

    # ---- Override model via env var if --model supplied ----
    if args.model and not args.dry_run:
        import os
        backend = (args.backend or "ollama").lower()
        if backend == "ollama":
            os.environ["OLLAMA_MODEL_GENERATOR"] = args.model
        elif backend == "groq":
            os.environ["GROQ_MODEL"] = args.model

    # ---- Load WorkflowSpec ----
    try:
        spec = WorkflowSpec.from_file(spec_path)
        log.info(
            "WorkflowSpec loaded successfully",
            extra={
                "site": spec.workflow.site,
                "steps": len(spec.steps),
                "parameters": len(spec.parameters),
            },
        )
    except Exception as exc:
        print(f"[error] Failed to load or validate spec file: {exc}", file=sys.stderr)
        return 1

    # ---- Setup Orchestration ----
    output_path: Path = args.output
    if output_path.is_dir() or not output_path.suffix:
        output_dir = output_path
    else:
        output_dir = output_path.parent

    # Instantiate generator
    generator = CodeGenerator(
        dry_run=args.dry_run,
        backend=args.backend,
        max_retries=args.retries,
    )

    from browserbot.agents.validator.pipeline import ValidationPipeline
    from browserbot.agents.code_generator.coordinator import PipelineCoordinator

    pipeline = ValidationPipeline()
    coordinator = PipelineCoordinator(
        generator=generator,
        pipeline=pipeline,
        output_dir=output_dir,
    )

    print("\n[BrowserBot] Starting generated tool compilation and validation loop...")
    try:
        report = coordinator.run(spec)
        
        # Print stage summaries
        print(f"  Stage 1: File Existence      -> {'PASS' if report.file_existence.success else 'FAIL'}")
        print(f"  Stage 2: Python Compilation  -> {'PASS' if report.compilation.success else 'FAIL'}")
        print(f"  Stage 3: Import Check        -> {'PASS' if report.import_check.success else 'FAIL'}")
        print(f"  Stage 4: Runtime Dry-Run     -> {'PASS' if report.runtime_dry_run.success else 'FAIL'}")
        
        if not report.overall_success:
            failed_stage_msg = "Unknown error"
            if not report.file_existence.success:
                failed_stage_msg = report.file_existence.message
            elif not report.compilation.success:
                failed_stage_msg = report.compilation.message
            elif not report.import_check.success:
                failed_stage_msg = report.import_check.message
            elif not report.runtime_dry_run.success:
                failed_stage_msg = report.runtime_dry_run.message
            print(f"\n[error] Validation failed after maximum retry attempts. Reason: {failed_stage_msg}", file=sys.stderr)
            return 1
    except Exception as exc:
        print(f"[error] Failed during pipeline coordination: {exc}", file=sys.stderr)
        return 1

    print("[BrowserBot] Done. Server code generation, retry feedback loop, and validation completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
