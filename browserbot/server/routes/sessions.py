"""
browserbot/server/routes/sessions.py — REST API router for managing wizard sessions.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from browserbot.config.settings import settings
from browserbot.models.action_log import ActionLog
from browserbot.models.workflow_spec import WorkflowSpec
from browserbot.recorder.convert_codegen import convert_codegen_file
from browserbot.recorder.scrubber import scrub
from browserbot.agents.pattern_extractor.extractor import PatternExtractor
from browserbot.agents.pattern_extractor.generator import generate_workflow_spec
from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.agents.validator.pipeline import ValidationPipeline
from browserbot.agents.code_generator.coordinator import PipelineCoordinator
from browserbot.agents.packager.packager import Packager
from browserbot.agents.code_generator.manifest import MCPToolManifest
from browserbot.server.db import SessionStateStore
from browserbot.server.schemas import (
    RecordRequest,
    SessionResponse,
    ConfirmRequest,
    GenerateRequest,
    PackageRequest,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])


def _playwright_exe() -> str:
    """Return the path to the playwright executable inside the active virtualenv."""
    venv_playwright = Path(sys.executable).parent / "playwright"
    if venv_playwright.exists():
        return str(venv_playwright)
    venv_playwright_exe = Path(sys.executable).parent / "playwright.exe"
    if venv_playwright_exe.exists():
        return str(venv_playwright_exe)
    return "playwright"


def run_recording_in_background(
    session_id: str,
    url: str | None,
    workflow_hint: str | None,
    raw_script_path: Path,
    session_json_path: Path,
):
    """Subprocess runner for Playwright codegen window, followed by auto-scrub and save."""
    pw = _playwright_exe()
    cmd = [
        pw,
        "codegen",
        "--target", "python",
        "--output", str(raw_script_path),
        "--browser", "chromium",
    ]
    if url:
        cmd.append(url)

    log.info(
        "Launching Playwright codegen in background task",
        extra={"session_id": session_id, "cmd": " ".join(cmd)}
    )

    try:
        res = subprocess.run(cmd, check=False)
        if res.returncode != 0:
            log.error("Playwright codegen process exited non-zero", extra={"session_id": session_id, "code": res.returncode})
            db = SessionStateStore()
            db.update_session(session_id, "failed")
            return
    except Exception as exc:
        log.error("Failed to run playwright codegen subprocess", extra={"session_id": session_id, "error": str(exc)})
        db = SessionStateStore()
        db.update_session(session_id, "failed")
        return

    if not raw_script_path.exists() or raw_script_path.stat().st_size == 0:
        log.error("Playwright raw script is missing or empty after recording", extra={"session_id": session_id})
        db = SessionStateStore()
        db.update_session(session_id, "failed")
        return

    try:
        # Convert raw playwright script to ActionLog schema
        site = ""
        if url:
            parsed = urllib.parse.urlparse(url)
            site = parsed.netloc or ""

        action_log = convert_codegen_file(
            raw_script_path,
            site=site,
            session_id=session_id,
            recorded_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            workflow_hint=workflow_hint,
        )

        # Redact any PII/secrets before writing to disk
        scrub_result = scrub(action_log)
        scrubbed_log = scrub_result.action_log
        scrubbed_log.to_file(session_json_path)

        # Save secrets map to git-ignored JSON file if secrets were found
        if scrub_result.value_map:
            secrets_path = session_json_path.parent / f"{session_id}_secrets.json"
            reverse_map = {v: k for k, v in scrub_result.value_map.items()}
            with open(secrets_path, "w", encoding="utf-8") as f:
                json.dump(reverse_map, f, indent=2)

        # Update Session State DB
        db = SessionStateStore()
        sess = db.get_session(session_id)
        if sess:
            paths = sess["artifact_paths"]
            if scrub_result.value_map:
                paths["secrets"] = str(session_json_path.parent / f"{session_id}_secrets.json")
            db.update_session(session_id, "recorded", paths)

        log.info("Background recording session completed and converted successfully", extra={"session_id": session_id})

    except Exception as exc:
        log.error("Exception during background recording conversion", extra={"session_id": session_id, "error": str(exc)})
        db = SessionStateStore()
        db.update_session(session_id, "failed")


@router.post("/record", response_model=SessionResponse)
async def record_session(req: RecordRequest, background_tasks: BackgroundTasks):
    """Starts a new recording session and opens the Playwright codegen browser."""
    now = datetime.now(timezone.utc)
    session_id = f"session_{now.strftime('%Y%m%dT%H%M%S')}"
    
    out_dir = settings.sessions_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_script_path = out_dir / f"{session_id}_raw.py"
    session_json_path = out_dir / f"{session_id}.json"

    artifact_paths = {
        "raw_script": str(raw_script_path),
        "action_log": str(session_json_path),
    }

    db = SessionStateStore()
    sess = db.create_session(session_id, "recording", artifact_paths)

    background_tasks.add_task(
        run_recording_in_background,
        session_id=session_id,
        url=req.url,
        workflow_hint=req.workflow_hint,
        raw_script_path=raw_script_path,
        session_json_path=session_json_path,
    )

    return SessionResponse(**sess)


@router.get("", response_model=list[SessionResponse])
async def list_sessions():
    """Lists all sessions in the local state store."""
    db = SessionStateStore()
    return [SessionResponse(**s) for s in db.list_sessions()]


@router.get("/{id}", response_model=SessionResponse)
async def get_session(id: str):
    """Retrieves state details for a specific session."""
    db = SessionStateStore()
    sess = db.get_session(id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {id} not found")
    return SessionResponse(**sess)


@router.post("/{id}/extract")
async def extract_parameters(id: str, dry_run: bool = True):
    """Runs PatternExtractor on the recorded action log."""
    db = SessionStateStore()
    sess = db.get_session(id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {id} not found")

    action_log_path = Path(sess["artifact_paths"]["action_log"])
    if not action_log_path.exists():
        raise HTTPException(status_code=400, detail=f"Action log file not found at: {action_log_path}")

    # Load and scrub log
    action_log = ActionLog.from_file(action_log_path)
    scrub_result = scrub(action_log)
    scrubbed_log = scrub_result.action_log

    extractor = PatternExtractor(dry_run=dry_run)
    extractor_output = extractor.extract(scrubbed_log)

    extractor_output_path = action_log_path.parent / f"{id}_extractor_output.json"
    extractor_output_path.write_text(extractor_output.model_dump_json(indent=2), encoding="utf-8")

    paths = sess["artifact_paths"]
    paths["extractor_output"] = str(extractor_output_path)
    db.update_session(id, "extracted", paths)

    return json.loads(extractor_output_path.read_text(encoding="utf-8"))


@router.post("/{id}/confirm")
async def confirm_parameters(id: str, req: ConfirmRequest, output_dir: str | None = None):
    """Saves parameter confirmations and compiles the WorkflowSpec IR."""
    db = SessionStateStore()
    sess = db.get_session(id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {id} not found")

    action_log_path = Path(sess["artifact_paths"]["action_log"])
    if not action_log_path.exists():
        raise HTTPException(status_code=400, detail=f"Action log file not found at: {action_log_path}")

    action_log = ActionLog.from_file(action_log_path)
    scrub_result = scrub(action_log)
    scrubbed_log = scrub_result.action_log

    from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput
    from browserbot.agents.pattern_extractor.models import ExtractedParameter
    confirmed_params = []
    for p in req.parameters:
        confirmed_params.append(
            ExtractedParameter(
                name=p.name,
                example_value=str(p.example_value),
                log_step_index=p.log_step_index,
                description=p.description,
                is_sensitive=p.is_sensitive,
                is_optional=p.is_optional,
            )
        )
    confirmed_output = ConfirmedOutput(parameters=confirmed_params)

    confirmed_output_path = action_log_path.parent / f"{id}_confirmed_output.json"
    extractor_output = confirmed_output.to_extractor_output()
    confirmed_output_path.write_text(extractor_output.model_dump_json(indent=2), encoding="utf-8")

    spec = generate_workflow_spec(scrubbed_log, confirmed_output)

    if not output_dir:
        site = scrubbed_log.metadata.site or "unknown"
        site_sanitized = re.sub(r"[^a-zA-Z0-9]", "_", site).lower().strip("_")
        output_dir_path = settings.generated_tools_dir / site_sanitized
    else:
        output_dir_path = Path(output_dir)

    output_dir_path.mkdir(parents=True, exist_ok=True)
    spec_path = output_dir_path / "workflow_spec.json"
    spec.to_file(spec_path)

    paths = sess["artifact_paths"]
    paths["confirmed_output"] = str(confirmed_output_path)
    paths["workflow_spec"] = str(spec_path)
    paths["output_dir"] = str(output_dir_path)
    db.update_session(id, "confirmed", paths)

    return json.loads(spec_path.read_text(encoding="utf-8"))


@router.post("/{id}/generate")
async def generate_code(id: str, req: GenerateRequest, dry_run: bool = True):
    """Executes the pipeline retry coordinator to produce validated server files."""
    db = SessionStateStore()
    sess = db.get_session(id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {id} not found")

    spec_path = Path(sess["artifact_paths"]["workflow_spec"])
    if not spec_path.exists():
        raise HTTPException(status_code=400, detail=f"Workflow spec not found at: {spec_path}")

    spec = WorkflowSpec.from_file(spec_path)
    output_dir_path = Path(req.output_dir or sess["artifact_paths"]["output_dir"])

    generator = CodeGenerator(dry_run=dry_run)
    pipeline = ValidationPipeline()
    coordinator = PipelineCoordinator(
        generator=generator,
        pipeline=pipeline,
        output_dir=output_dir_path,
    )

    secret_overrides = {}
    secrets_path = Path(sess["artifact_paths"]["action_log"]).parent / f"{id}_secrets.json"
    if secrets_path.exists():
        try:
            with open(secrets_path, "r", encoding="utf-8") as f:
                secret_overrides = json.load(f)
        except Exception as exc:
            log.warning("Failed to load secrets mapping", extra={"error": str(exc)})

    report = coordinator.run(spec, secret_overrides=secret_overrides)

    stage = "generated" if report.overall_success else "failed"
    paths = sess["artifact_paths"]
    paths["validation_report"] = str(output_dir_path / "validation_report.json")
    db.update_session(id, stage, paths)

    return json.loads(Path(paths["validation_report"]).read_text(encoding="utf-8"))


@router.post("/{id}/package")
async def package_tool(id: str, req: PackageRequest):
    """Packages the validated server script into an installable MCP structure."""
    db = SessionStateStore()
    sess = db.get_session(id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {id} not found")

    output_dir_path = Path(sess["artifact_paths"]["output_dir"])
    manifest_path = output_dir_path / "mcp_tool.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=400, detail="mcp_tool.json not found in output directory")

    manifest = MCPToolManifest.from_file(manifest_path)
    package_name = manifest.mcp_tool_name

    if not req.package_dir:
        package_dir_path = Path("packages") / package_name
    else:
        package_dir_path = Path(req.package_dir)

    packager = Packager()
    pkg = packager.package(output_dir_path, package_dir_path)
    verified = packager.verify_installation(package_dir_path)

    if not verified:
        db.update_session(id, "failed")
        raise HTTPException(status_code=500, detail="Package verification check failed")

    paths = sess["artifact_paths"]
    paths["package_dir"] = str(package_dir_path)
    paths["browserbot_package"] = str(package_dir_path / "browserbot_package.json")
    db.update_session(id, "packaged", paths)

    return json.loads(Path(paths["browserbot_package"]).read_text(encoding="utf-8"))


@router.post("/{id}/stage")
async def update_session_stage(id: str, stage: str):
    """Updates the stage of the session in the database state."""
    db = SessionStateStore()
    sess = db.get_session(id)
    if not sess:
        raise HTTPException(status_code=404, detail=f"Session {id} not found")
    db.update_session(id, stage, sess["artifact_paths"])
    return db.get_session(id)
