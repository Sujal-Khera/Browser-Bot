"""
browserbot/recorder/codegen_runner.py — Step 2.3: Playwright Codegen subprocess wrapper.

This module is responsible for:

1. Launching `playwright codegen` as a subprocess with the correct flags.
2. Waiting for the user to finish recording and close the browser.
3. Reading back the generated Python script file.
4. Invoking the converter (convert_codegen.py) to produce the Action Log.
5. Writing the session_<timestamp>.json file to the sessions directory.

It does NOT:
- parse or interpret the Playwright script (that is convert_codegen.py)
- perform PII scrubbing (that is Step 2.4)
- interact with any LLM
- implement any UI beyond the CLI output

SUBPROCESS DESIGN
-----------------
`playwright codegen` opens a visible Chromium browser window and an inspector
panel.  When the user closes the browser, the process exits and writes the
generated script to the -o file.  This module:

  1. Creates a temp file path for the raw script.
  2. Launches: playwright codegen --target python -o <tmp_path> [url]
  3. Streams the subprocess stdout/stderr to the terminal so the user can
     see any Playwright messages.
  4. On process exit, reads <tmp_path> and passes it to the converter.

The raw script file is kept alongside the session JSON so it can be
inspected or re-converted without re-recording.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from browserbot.config.settings import settings
from browserbot.logging import get_logger
from browserbot.models.action_log import ActionLogValidator
from browserbot.recorder.convert_codegen import convert_codegen_file
from browserbot.recorder.scrubber import scrub

log = get_logger(__name__)


def _playwright_exe() -> str:
    """
    Return the path to the playwright executable inside the active virtualenv.

    Falls back to searching PATH if the venv-local binary is not found.
    """
    # Prefer venv-local playwright (same Python environment as the project)
    venv_playwright = Path(sys.executable).parent / "playwright"
    if venv_playwright.exists():
        return str(venv_playwright)
    # Windows: .exe extension
    venv_playwright_exe = Path(sys.executable).parent / "playwright.exe"
    if venv_playwright_exe.exists():
        return str(venv_playwright_exe)
    # Fall back to PATH
    return "playwright"


def run_recording_session(
    *,
    url: str | None = None,
    workflow_hint: str | None = None,
    output_dir: Path | None = None,
) -> Path:
    """
    Launch Playwright codegen, wait for the user to finish, then convert.

    This is the complete Step 2.3 pipeline:

        playwright codegen -> raw_script.py -> converter -> session_<ts>.json

    Args:
        url:           Optional starting URL to open in the browser.
        workflow_hint: Optional description shown in the session metadata.
        output_dir:    Directory to write session files (default: settings.sessions_dir).

    Returns:
        Path to the written ``session_<timestamp>.json`` file.

    Raises:
        RuntimeError: If playwright codegen exits with a non-zero code.
        ValueError:   If the converter produces an invalid Action Log.
    """
    now = datetime.now(tz=timezone.utc)
    session_id = f"session_{now.strftime('%Y%m%dT%H%M%S')}"
    recorded_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    out_dir = output_dir or settings.sessions_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Paths for this session
    raw_script_path = out_dir / f"{session_id}_raw.py"
    session_json_path = out_dir / f"{session_id}.json"

    # Build the subprocess command
    pw = _playwright_exe()
    cmd: list[str] = [
        pw,
        "codegen",
        "--target", "python",
        "--output", str(raw_script_path),
        "--browser", "chromium",
    ]
    if url:
        cmd.append(url)

    log.info(
        "Launching Playwright codegen",
        extra={"session_id": session_id, "url": url or "(none)", "cmd": " ".join(cmd)},
    )

    print(f"\n[BrowserBot Recorder]")
    print(f"  Session  : {session_id}")
    print(f"  Output   : {session_json_path}")
    if url:
        print(f"  Start URL: {url}")
    print()
    print("  Chromium will open with the Playwright Inspector.")
    print("  Perform your workflow, then CLOSE the browser window to stop recording.")
    print()

    # Launch and wait — inherit stdio so the user sees Playwright messages
    try:
        result = subprocess.run(cmd, check=False)
    except FileNotFoundError:
        raise RuntimeError(
            f"Could not find playwright executable at: {pw}\n"
            "Run: uv run playwright install chromium"
        )

    if result.returncode != 0:
        log.error(
            "playwright codegen exited non-zero",
            extra={"session_id": session_id, "returncode": result.returncode},
        )
        raise RuntimeError(
            f"playwright codegen exited with code {result.returncode}. "
            f"Check the terminal output for details."
        )

    if not raw_script_path.exists() or raw_script_path.stat().st_size == 0:
        log.error(
            "Generated script missing or empty after codegen",
            extra={"session_id": session_id, "path": str(raw_script_path)},
        )
        raise RuntimeError(
            f"Expected generated script at {raw_script_path} but it is missing or empty.\n"
            "Did you close the browser before performing any actions?"
        )

    log.info(
        "Codegen complete, starting conversion",
        extra={
            "session_id": session_id,
            "raw_script": str(raw_script_path),
        },
    )

    print(f"[BrowserBot Recorder] Recording complete. Converting to Action Log...")

    # Infer site from URL if provided
    site = ""
    if url:
        parsed = urllib.parse.urlparse(url)
        site = parsed.netloc or ""

    # Convert the raw script to an ActionLog
    action_log = convert_codegen_file(
        raw_script_path,
        site=site,
        session_id=session_id,
        recorded_at=recorded_at,
        workflow_hint=workflow_hint,
    )

    # Scrub sensitive values — NOTHING reaches disk before this step
    scrub_result = scrub(action_log)
    if scrub_result.scrubbed_count > 0:
        log.info(
            "Sensitive fields redacted before disk write",
            extra={
                "session_id": session_id,
                "scrubbed": scrub_result.scrubbed_count,
                "secrets": scrub_result.secret_count,
            },
        )
        print(
            f"[BrowserBot Recorder] "
            f"{scrub_result.scrubbed_count} sensitive field(s) redacted "
            f"({scrub_result.secret_count} unique secret(s))."
        )

    # Re-validate after scrubbing — guarantees the file written to disk is always
    # schema-valid, even if the scrubber changed is_sensitive flags.
    scrubbed_log = scrub_result.action_log
    assert scrubbed_log is not None  # always set by Scrubber.scrub()
    _validator = ActionLogValidator()
    _validator.assert_valid(
        scrubbed_log.model_dump(mode="json", exclude_none=True),
        label=f"{session_id} (post-scrub)",
    )

    scrubbed_log.to_file(session_json_path)

    log.info(
        "Session saved",
        extra={
            "session_id": session_id,
            "steps": len(scrubbed_log.steps),
            "path": str(session_json_path),
        },
    )

    print(f"[BrowserBot Recorder] Session saved:")
    print(f"  JSON : {session_json_path}")
    print(f"  Steps: {len(scrubbed_log.steps)}")
    print(f"  Raw  : {raw_script_path}")
    print()

    return session_json_path
