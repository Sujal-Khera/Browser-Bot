"""
tests/fixtures/nobuycart_tracking_script.py — Step 1.3 ground truth (NoBuyCart).

PURPOSE
-------
This is the manually-written, hand-crafted Playwright automation for the
BrowserBot MVP demo workflow, targeting the NoBuyCart fake delivery tracker.

Website: https://nobuycart.com/tracking/
No login, no username, no password required.

WORKFLOW
--------
1. Open https://nobuycart.com/tracking/
2. Enter a fake order code (e.g. NBC-2026-8F3K2Q) into the "Fake order code" field
3. Click "Show fake timeline"
4. Wait for the tracking timeline to render
5. Extract all timeline step headings
6. Print the result to stdout

DEMO SITE NOTES
---------------
NoBuyCart is a fake delivery tracking simulator. Any order code generates a
simulated shipment timeline — no login, no payment, no real delivery.

The example order code shown on the page is: NBC-2026-8F3K2Q
Any string can be entered — the site always generates a fictional timeline.

The React/Astro component renders the results client-side after form submission.
All Playwright waits target the rendered DOM state, not page navigation.

RELIABILITY BASELINE (Step 1.3 verification)
---------------------------------------------
Run 10 consecutive times to establish the Phase 9 baseline success rate:

    Windows PowerShell:
        for ($i=1; $i -le 10; $i++) {
            python tests/fixtures/nobuycart_tracking_script.py
        }

    Linux / macOS:
        for i in {1..10}; do python tests/fixtures/nobuycart_tracking_script.py; done

USAGE
-----
    python tests/fixtures/nobuycart_tracking_script.py
    python tests/fixtures/nobuycart_tracking_script.py --headed       # visible browser
    python tests/fixtures/nobuycart_tracking_script.py --order-id ABC-1234

Expected output (success):
    Tracking result for: NBC-2026-8F3K2Q
    Timeline steps (6):
      1. Fake order received
      2. Packed in the imaginary warehouse
      3. Courier picked it up emotionally
      4. Package took a scenic route
      5. Delayed by fictional customs
      6. Final status: happily never delivered
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env (optional)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    _dotenv = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=_dotenv, override=False)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration — overridable via environment variables or CLI flags
# ---------------------------------------------------------------------------

DEMO_URL: str = "https://nobuycart.com/tracking/"

# The example order code shown on the page itself.
# Any string works — the site always generates a timeline.
DEFAULT_ORDER_ID: str = os.getenv(
    "BROWSERBOT_DEMO_ORDER_ID",
    "NBC-2026-8F3K2Q",
)

PAGE_LOAD_TIMEOUT_MS: int = int(os.getenv("BROWSERBOT_PAGE_TIMEOUT_MS", "30000"))
ACTION_TIMEOUT_MS: int = int(os.getenv("BROWSERBOT_ACTION_TIMEOUT_MS", "15000"))
HEADLESS: bool = os.getenv("BROWSERBOT_HEADLESS", "true").lower() in (
    "1",
    "true",
    "yes",
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class TrackingResult:
    """Structured result extracted from the NoBuyCart tracking page."""

    order_id: str
    timeline_steps: list[str] = field(default_factory=list)
    final_status: str = ""
    raw_heading: str = ""  # the h2 shown in the result panel


# ---------------------------------------------------------------------------
# Core automation
# ---------------------------------------------------------------------------


async def track_order(order_id: str, *, headed: bool = False) -> TrackingResult:
    """
    Perform the complete fake order tracking workflow on NoBuyCart.

    Workflow:
        1. Navigate to https://nobuycart.com/tracking/
        2. Fill "Fake order code" input with ``order_id``
        3. Click "Show fake timeline" submit button
        4. Wait for the timeline list items (``li.status-card``) to render
        5. Extract all step headings (``h3`` inside each ``li.status-card``)
        6. Return a structured :class:`TrackingResult`

    Args:
        order_id: The fake order code to look up.
        headed:   If True, run in a visible browser window.

    Returns:
        :class:`TrackingResult` with the extracted timeline steps.

    Raises:
        RuntimeError: If any automation step fails.
    """
    from playwright.async_api import Page, async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=not headed)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        page: Page = await context.new_page()

        page.set_default_timeout(ACTION_TIMEOUT_MS)
        page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT_MS)

        try:
            # ----------------------------------------------------------------
            # Step 1: Navigate to the tracking page
            # ----------------------------------------------------------------
            await page.goto(DEMO_URL, wait_until="networkidle")

            # ----------------------------------------------------------------
            # Step 2: Fill the "Fake order code" input
            #
            # The input field has no id or name attribute in the source HTML.
            # It is identified by its visible label text "Fake order code"
            # using Playwright's get_by_label semantic locator — the most
            # robust selector available for this element.
            #
            # Source HTML reference:
            #   <label class="grid gap-2 text-sm font-bold">
            #     Fake order code
            #     <input class="min-h-12 rounded-lg border border-line px-3
            #                   text-base uppercase"
            #            placeholder="NBC-2026-8F3K2Q" value=""/>
            #   </label>
            # ----------------------------------------------------------------
            order_input = page.get_by_label("Fake order code")
            await order_input.clear()
            await order_input.fill(order_id)

            # ----------------------------------------------------------------
            # Step 3: Click the "Show fake timeline" submit button
            #
            # Source HTML reference:
            #   <button class="button-primary" type="submit">
            #     <svg .../>
            #     Show fake timeline
            #   </button>
            # ----------------------------------------------------------------
            await page.get_by_role("button", name="Show fake timeline").click()

            # ----------------------------------------------------------------
            # Step 4: Wait for the timeline to render
            #
            # The React/Astro component renders timeline items as:
            #   <li class="status-card grid grid-cols-[34px_1fr] gap-3">
            #     <span class="timeline-dot">N</span>
            #     <div>
            #       <h3 class="font-black">Step heading text</h3>
            #       <p class="text-sm text-muted">Pretend checkpoint updated...</p>
            #     </div>
            #   </li>
            #
            # Wait for at least one status-card to be visible before
            # extracting — this handles the client-side rendering delay.
            # ----------------------------------------------------------------
            await page.wait_for_selector("li.status-card", state="visible")

            # ----------------------------------------------------------------
            # Step 5: Extract the order ID heading from the result panel
            #
            # Source HTML reference:
            #   <h2 class="mt-1 text-3xl font-black">NBC-2026-8F3K2Q</h2>
            # This is the h2 directly inside the result panel header div.
            # ----------------------------------------------------------------
            # The result panel h2 always shows the tracked order code.
            # Use a more specific selector to avoid matching "Track a fake order"
            # (the form's h2).
            result_heading_el = page.locator(
                "div.surface.overflow-hidden h2"
            ).first
            raw_heading: str = (await result_heading_el.inner_text()).strip()

            # ----------------------------------------------------------------
            # Step 6: Extract all timeline step headings
            #
            # Each <li class="status-card"> contains an <h3> with the step name.
            # The page always renders exactly 6 steps for the NoBuyCart simulator.
            # ----------------------------------------------------------------
            step_elements = page.locator("li.status-card h3")
            step_count: int = await step_elements.count()

            timeline_steps: list[str] = []
            for i in range(step_count):
                step_text: str = (await step_elements.nth(i).inner_text()).strip()
                timeline_steps.append(step_text)

            # The last step is the final status.
            final_status: str = timeline_steps[-1] if timeline_steps else ""

            return TrackingResult(
                order_id=order_id,
                timeline_steps=timeline_steps,
                final_status=final_status,
                raw_heading=raw_heading,
            )

        except Exception as exc:
            # Save a failure screenshot for debugging.
            screenshot_path = Path(__file__).parent / "failure_screenshot.png"
            try:
                await page.screenshot(path=str(screenshot_path))
                print(
                    f"  Screenshot saved to: {screenshot_path}",
                    file=sys.stderr,
                )
            except Exception:  # noqa: BLE001
                pass
            raise RuntimeError(
                f"NoBuyCart tracking script failed: {exc}"
            ) from exc

        finally:
            await context.close()
            await browser.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python tests/fixtures/nobuycart_tracking_script.py",
        description="BrowserBot ground truth — NoBuyCart fake order tracker (Step 1.3)",
    )
    parser.add_argument(
        "--order-id",
        default=DEFAULT_ORDER_ID,
        metavar="CODE",
        help=f"Fake order code to track (default: {DEFAULT_ORDER_ID})",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run in a visible browser window instead of headless mode.",
    )
    return parser.parse_args()


def main() -> None:
    """
    Run the NoBuyCart order tracking workflow and print the result to stdout.

    Prints the scraped timeline steps to stdout (Step 1.3 requirement).
    Exits 0 on success, 1 on failure.
    """
    args = _parse_args()

    order_id: str = args.order_id.strip().upper()
    headed: bool = args.headed or not HEADLESS

    start = time.perf_counter()

    print(f"\nBrowserBot -- NoBuyCart Ground Truth Script (Step 1.3)")
    print(f"URL      : {DEMO_URL}")
    print(f"Order ID : {order_id}")
    print(f"Headless : {not headed}")
    print("-" * 55)

    try:
        result: TrackingResult = asyncio.run(track_order(order_id, headed=headed))
        elapsed = time.perf_counter() - start

        print(f"\n[PASS] Tracking result for: {result.raw_heading}")
        print(f"Timeline steps ({len(result.timeline_steps)}):")
        for i, step in enumerate(result.timeline_steps, 1):
            print(f"  {i}. {step}")

        print(f"\nFinal status : {result.final_status}")
        print(f"Elapsed      : {elapsed:.2f}s")

    except RuntimeError as exc:
        elapsed = time.perf_counter() - start
        print(f"\n[FAIL] Script failed ({elapsed:.2f}s)")
        print(f"  {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
