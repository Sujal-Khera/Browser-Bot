"""
browserbot/recorder/__main__.py — entry point for `python -m browserbot.recorder`.

Subcommands
-----------

    python -m browserbot.recorder start [URL]
        Launch Playwright codegen, wait for the user to record a workflow,
        then convert the generated script to a BrowserBot session JSON.

        Options:
            --url URL           Starting URL for the browser.
            --hint TEXT         Workflow description stored in session metadata.
            --output-dir DIR    Directory for session files (default: workflows/sessions/).

        Example:
            python -m browserbot.recorder start https://nobuycart.com/tracking/

    python -m browserbot.recorder --demo
        Run a Playwright smoke-test to verify the environment (Step 1.1).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from browserbot.logging import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Demo (Step 1.1 smoke-test)
# ---------------------------------------------------------------------------


async def _run_demo(*, headed: bool) -> None:
    """Playwright smoke-test: navigate to example.com and confirm a title."""
    from playwright.async_api import async_playwright

    log.info("Recorder demo: launching Chromium (headed=%s)", headed)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        page = await browser.new_page()

        target_url = "https://example.com"
        log.info("Recorder demo: navigating to %s", target_url)

        await page.goto(target_url)
        title: str = await page.title()

        await browser.close()

    log.info("Recorder demo: page title = %r", title)
    print(f"\n[PASS]  Playwright smoke-test passed -- page title: {title!r}")
    print("        Chromium is installed and working correctly.")


# ---------------------------------------------------------------------------
# Start (Step 2.3 recording session)
# ---------------------------------------------------------------------------


def _cmd_start(args: argparse.Namespace) -> None:
    """Handle `python -m browserbot.recorder start`."""
    from browserbot.recorder.codegen_runner import run_recording_session

    output_dir: Path | None = Path(args.output_dir) if args.output_dir else None

    try:
        session_path = run_recording_session(
            url=args.url or None,
            workflow_hint=args.hint or None,
            output_dir=output_dir,
        )
        print(f"[OK] Session written to: {session_path}")
    except (RuntimeError, ValueError) as exc:
        print(f"\n[FAIL] Recording session failed:\n  {exc}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m browserbot.recorder",
        description="BrowserBot Recorder — capture browser workflows as structured Action Logs.",
    )

    # Legacy --demo flag (Step 1.1)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a Playwright smoke-test (Chromium + example.com) and exit.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Open a visible browser window (only applies to --demo).",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # --- start ---
    start_parser = subparsers.add_parser(
        "start",
        help="Launch Playwright codegen, record a workflow, produce session_<ts>.json.",
    )
    start_parser.add_argument(
        "url",
        nargs="?",
        default=None,
        metavar="URL",
        help="Starting URL for the browser (optional — you can navigate inside Chromium).",
    )
    start_parser.add_argument(
        "--hint",
        default=None,
        metavar="TEXT",
        help="Short description of the workflow (stored in session metadata).",
    )
    start_parser.add_argument(
        "--output-dir",
        default=None,
        metavar="DIR",
        help="Directory to write session files (default: workflows/sessions/).",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.demo:
        asyncio.run(_run_demo(headed=args.headed))
        return

    if args.command == "start":
        _cmd_start(args)
        return

    # No subcommand — print help
    parser.print_help()
    print(
        "\nTo start recording: python -m browserbot.recorder start [URL]",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
