"""
browserbot/agents/pattern_extractor/__main__.py — Step 3.1 CLI entry point.

Usage:
    # Dry-run (no LLM) — shows extracted parameters without calling Ollama
    python -m browserbot.agents.pattern_extractor --dry-run workflows/sessions/session_X.json

    # Real extraction via Ollama (default backend)
    python -m browserbot.agents.pattern_extractor workflows/sessions/session_X.json

    # Override backend
    python -m browserbot.agents.pattern_extractor --backend groq workflows/sessions/session_X.json

    # Override model
    python -m browserbot.agents.pattern_extractor --model llama3.1:8b session.json

    # Skip confirmation (auto-accept all)
    python -m browserbot.agents.pattern_extractor --yes session.json

    # Print confirmed output as JSON (for pipeline integration)
    python -m browserbot.agents.pattern_extractor --dry-run --json session.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from browserbot.agents.pattern_extractor.confirmer import confirm_parameters
from browserbot.agents.pattern_extractor.extractor import ExtractionError, PatternExtractor
from browserbot.logging import get_logger
from browserbot.models.action_log import ActionLog

log = get_logger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m browserbot.agents.pattern_extractor",
        description="BrowserBot Phase 3 — Pattern Extractor",
    )
    p.add_argument(
        "session_file",
        type=Path,
        help="Path to a session_<timestamp>.json file produced by the Recorder.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Skip the LLM call and produce a stub output (all fill steps = parameters).",
    )
    p.add_argument(
        "--backend",
        choices=["ollama", "groq"],
        default=None,
        help="LLM backend to use. Defaults to BROWSERBOT_LLM_BACKEND env var (ollama).",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override the model name (e.g. 'llama3.1:8b'). Sets OLLAMA_MODEL_EXTRACTOR.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Auto-confirm all parameters without interactive prompting.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        default=False,
        dest="output_json",
        help="Print the confirmed output as JSON to stdout (for pipeline integration).",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=None,
        help="Maximum number of LLM retries on malformed output (default: from settings).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    session_path: Path = args.session_file
    if not session_path.exists():
        print(f"[error] File not found: {session_path}", file=sys.stderr)
        return 1

    # ---- Override model via env var if --model supplied ----
    if args.model and not args.dry_run:
        import os
        backend = (args.backend or "ollama").lower()
        if backend == "ollama":
            os.environ["OLLAMA_MODEL_EXTRACTOR"] = args.model
        elif backend == "groq":
            os.environ["GROQ_MODEL"] = args.model

    # ---- Load the ActionLog ----
    try:
        action_log = ActionLog.from_file(session_path)
        log.info(
            "Session loaded",
            extra={
                "session_id": action_log.metadata.session_id,
                "steps": len(action_log.steps),
                "site": action_log.metadata.site,
            },
        )
    except Exception as exc:
        print(f"[error] Failed to load session file: {exc}", file=sys.stderr)
        return 1

    # ---- Run the Pattern Extractor ----
    extractor = PatternExtractor(
        dry_run=args.dry_run,
        backend=args.backend,
        max_retries=args.retries,
    )

    try:
        extractor_output = extractor.extract(action_log)
    except ExtractionError as exc:
        print(f"\n[BrowserBot] Pattern extraction failed: {exc}", file=sys.stderr)
        if exc.errors:
            print("Last errors:\n" + "\n".join(f"  • {e}" for e in exc.errors), file=sys.stderr)
        return 1

    # ---- Parameter Confirmation (Step 3.2) ----
    try:
        confirmed = confirm_parameters(
            extractor_output,
            auto_confirm=args.yes,
        )
    except KeyboardInterrupt:
        print("\n\n[BrowserBot] Confirmation cancelled by user.", file=sys.stderr)
        return 1

    # ---- Output ----
    if args.output_json:
        output_data = confirmed.to_extractor_output().model_dump(mode="json", exclude_none=True)
        print(json.dumps(output_data, indent=2))

    print("\n[BrowserBot] Done. Confirmed output ready for Phase 4 (Code Generator).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
