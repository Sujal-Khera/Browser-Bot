"""
browserbot/orchestrator/self_healing.py — Phase 8B: Self-Healing.

Implements automated self-healing for generated MCP packages that encounter
runtime failures or selector drift.
"""

from __future__ import annotations

import os
from pathlib import Path
from browserbot.logging import get_logger
from browserbot.models.package import BrowserBotPackage
from browserbot.orchestrator.pipeline import OrchestrationPipeline, PipelineOrchestrationError

log = get_logger(__name__)


def self_heal_package(
    package_dir: Path | str,
    *,
    registry_config_path: Path | str | None = None,
    force: bool = False,
) -> bool:
    """
    Attempts to self-heal a package by locating its original recorded session log,
    re-running the orchestration pipeline (scrubbing, pattern extraction, AST validation,
    compilation, and verification), and re-installing the updated server.

    Args:
        package_dir: Path to the packaged BrowserBot tool directory.
        registry_config_path: Custom path to the Claude config JSON (for testing).
        force: If True, self-heal even if needs_healing.flag is absent.

    Returns:
        True if the self-healing succeeded and the package is verified healthy.
    """
    package_dir = Path(package_dir).resolve()
    manifest_path = package_dir / "browserbot_package.json"
    flag_path = package_dir / "needs_healing.flag"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Package manifest not found: {manifest_path}")

    # Check if self-healing is triggered (flag exists or force=True)
    if not flag_path.exists() and not force:
        log.info("No healing flag found. Package is healthy. Skipping self-heal.", extra={"package": str(package_dir)})
        return False

    log.info("Self-healing triggered for package", extra={"package": str(package_dir), "force": force})

    try:
        # 1. Load package details
        package = BrowserBotPackage.from_file(manifest_path)
        session_id = package.metadata.source_session_id

        # 2. Locate original session log file
        session_log_path = None
        candidates = [
            Path("workflows/sessions") / f"{session_id}.json",
            Path("workflows/sessions") / f"session_{session_id}.json",
            Path("workflows/sessions") / f"{session_id}",
        ]
        for c in candidates:
            if c.exists():
                session_log_path = c
                break

        if not session_log_path:
            # Fallback recursive lookup in workflows/
            for path in Path("workflows").rglob(f"*{session_id}*.json"):
                session_log_path = path
                break

        if not session_log_path or not session_log_path.exists():
            raise FileNotFoundError(
                f"Could not locate original action log for session ID '{session_id}' in workflows/ directory."
            )

        log.info("Original action log located", extra={"path": str(session_log_path)})

        # 3. Determine output directory (reconstruct from package info or default)
        output_dir = Path("generated_tools") / package.package_name.replace("execute_", "")
        output_dir.mkdir(parents=True, exist_ok=True)

        # 4. Re-run orchestration pipeline with same settings
        pipeline = OrchestrationPipeline(dry_run=True)
        pipeline.run(
            raw_action_log_path=session_log_path,
            output_dir=output_dir,
            package_dir=package_dir,
            register=True,
            registry_config_path=registry_config_path,
        )

        # 5. Clear flag file on success
        if flag_path.exists():
            flag_path.unlink()
            log.info("Self-healing flag cleared successfully", extra={"path": str(flag_path)})

        log.info("Self-healing completed successfully", extra={"package": str(package_dir)})
        return True

    except Exception as exc:
        log.error("Self-healing failed", extra={"package": str(package_dir), "error": str(exc)})
        raise
