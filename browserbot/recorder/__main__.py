"""
browserbot.recorder.__main__ — entry point for `python -m browserbot.recorder`.

Phase 1 deliverable (Step 1.1 exit criteria):
    `python -m browserbot.recorder --demo` must run without error.

The --demo flag verifies the Playwright installation by opening a headless
Chromium browser, navigating to example.com, and confirming a page title
is returned.  It does NOT implement the recording pipeline (Phase 2).

Usage:
    python -m browserbot.recorder --demo
    python -m browserbot.recorder --demo --headed    # visible browser
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from browserbot.logging import get_logger

log = get_logger(__name__)


async def _run_demo(*, headed: bool) -> None:
    """
    Playwright smoke-test: navigate to example.com and confirm a title is found.

    This proves:
        1. Playwright is installed and importable.
        2. Chromium is installed (playwright install chromium was run).
        3. The async Playwright API works end-to-end.

    Args:
        headed: If True, run in visible (non-headless) browser mode.
    """
    from playwright.async_api import async_playwright  # local import — heavy

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


def main() -> None:
    """CLI entry point for `python -m browserbot.recorder`."""
    parser = argparse.ArgumentParser(
        prog="python -m browserbot.recorder",
        description=(
            "BrowserBot recorder module.  "
            "Phase 1: use --demo to verify your Playwright installation."
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run a Playwright smoke-test (Chromium + example.com) and exit.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Open a visible browser window instead of running headless.",
    )

    args = parser.parse_args()

    if not args.demo:
        parser.print_help()
        print(
            "\nNote: Full recording functionality is implemented in Phase 2. "
            "Run with --demo to verify your Playwright installation.",
            file=sys.stderr,
        )
        sys.exit(0)

    asyncio.run(_run_demo(headed=args.headed))


if __name__ == "__main__":
    main()
