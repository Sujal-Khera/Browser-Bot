"""
browserbot/runtime/resilience.py — Phase 8: Selector Resilience and Network/Timing Resilience.

Implements:
1. Step 8.1: Prioritized locator fallback strategy (resolve_locator)
2. Step 8.4: Explicit wait triggers (wait_for_load_state) and action-retry loop with backoff
"""

from __future__ import annotations

import asyncio
from typing import Any
from playwright.async_api import Page, Locator
from browserbot.logging import get_logger

log = get_logger(__name__)


async def resolve_locator(
    page: Page,
    selector: dict[str, Any],
    timeout_ms: int = 3000,
) -> Locator:
    """
    Deterministically resolves a locator using a prioritized fallback selector strategy.
    Implicitly waits for the page network activity to settle first.

    Candidate Priority Order:
    1. ARIA Role (if role/aria_role details are provided)
    2. Label (form-associated labels)
    3. Placeholder (input-placeholder text matching name or value)
    4. Test ID (custom data-testid attributes)
    5. Text content (get_by_text matches)
    6. Raw Selector (brittle CSS/XPath fallback)

    Returns:
        The first locator candidate that successfully matches a visible/attached element.
        If no candidate resolves within the timeout, defaults to returning the primary candidate.
    """
    # Step 8.4: Wait for page load state to settle before attempting resolution
    try:
        await page.wait_for_load_state("networkidle", timeout=1500)
        log.info("Page network state settled (networkidle)")
    except Exception:
        # Ignore networkidle timeout to handle slow/noisy trackers gracefully
        pass

    strategy = selector.get("strategy")
    value = selector.get("value", "")
    aria_role = selector.get("aria_role")
    aria_name = selector.get("aria_name")

    candidates: list[tuple[str, Any]] = []

    # 1. Priority 1: ARIA Role locator
    if aria_role and aria_name:
        candidates.append((
            f"role: {aria_role} [name='{aria_name}']",
            lambda p: p.get_by_role(aria_role, name=aria_name)
        ))
    elif strategy == "role" and aria_role:
        candidates.append((
            f"role: {aria_role} [name='{value}']",
            lambda p: p.get_by_role(aria_role, name=value)
        ))

    # 2. Priority 2: Label locator
    if strategy == "label":
        candidates.append((
            f"label: '{value}'",
            lambda p: p.get_by_label(value)
        ))
    elif aria_name:
        candidates.append((
            f"label: '{aria_name}'",
            lambda p: p.get_by_label(aria_name)
        ))

    # 3. Priority 3: Placeholder locator
    if strategy == "placeholder":
        candidates.append((
            f"placeholder: '{value}'",
            lambda p: p.get_by_placeholder(value)
        ))
    elif aria_name:
        candidates.append((
            f"placeholder: '{aria_name}'",
            lambda p: p.get_by_placeholder(aria_name)
        ))

    # 4. Priority 4: Test ID locator
    if strategy == "test_id":
        candidates.append((
            f"test_id: '{value}'",
            lambda p: p.get_by_test_id(value)
        ))

    # 5. Priority 5: Text locator
    if strategy == "text":
        candidates.append((
            f"text: '{value}'",
            lambda p: p.get_by_text(value)
        ))
    elif aria_name:
        candidates.append((
            f"text: '{aria_name}'",
            lambda p: p.get_by_text(aria_name)
        ))

    # 6. Priority 6: Default raw locator (CSS/XPath)
    if value:
        candidates.append((
            f"selector: '{value}'",
            lambda p: p.locator(value)
        ))

    # Filter out duplicate candidates to preserve deterministic ordering
    seen: set[str] = set()
    unique_candidates: list[tuple[str, Any]] = []
    for name, locator_fn in candidates:
        if name not in seen:
            seen.add(name)
            unique_candidates.append((name, locator_fn))

    if not unique_candidates:
        raise RuntimeError(f"No selector candidates could be derived for selector: {selector}")

    # Log Constructed Candidates
    log.info(
        "Resolving locator with prioritized fallbacks",
        extra={"candidates": [c[0] for c in unique_candidates], "timeout_ms": timeout_ms}
    )

    # Poll candidates sequentially until one resolves to an attached element
    start_time = asyncio.get_event_loop().time()
    while True:
        for name, locator_fn in unique_candidates:
            try:
                loc = locator_fn(page)
                if await loc.count() > 0:
                    log.info("Locator resolved successfully", extra={"selected": name})
                    return loc
            except Exception:
                pass

        elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
        if elapsed >= timeout_ms:
            break
        await asyncio.sleep(0.1)

    # Default fallback: return the first candidate locator
    first_name, first_fn = unique_candidates[0]
    log.warning(
        "Fallback locator resolution timed out. Defaulting to first candidate.",
        extra={"default": first_name}
    )
    return first_fn(page)


async def resilient_click(
    page: Page,
    selector: dict[str, Any],
    timeout_ms: int = 5000,
) -> None:
    """
    Executes a resilient click action with selector resolution, explicit wait,
    and action retry-with-backoff to handle transient rendering/network jitter.
    """
    backoffs = [0.1, 0.5, 1.0, 2.0]
    last_exc = None

    for attempt, delay in enumerate(backoffs, start=1):
        try:
            # Step 8.1 + 8.4: Resolve locator and check visibility
            locator = await resolve_locator(page, selector, timeout_ms=1000)
            await locator.wait_for(state="visible", timeout=1500)
            await locator.click(timeout=1500)
            log.info("Resilient click succeeded", extra={"attempt": attempt})
            return
        except Exception as exc:
            last_exc = exc
            log.warning(
                "Click failed, retrying click with backoff",
                extra={"attempt": attempt, "delay": delay, "error": str(exc)}
            )
            await asyncio.sleep(delay)

    raise RuntimeError(
        f"Resilient click failed after {len(backoffs)} retries. "
        f"Last exception: {last_exc}"
    )


async def resilient_fill(
    page: Page,
    selector: dict[str, Any],
    value: str,
    timeout_ms: int = 5000,
) -> None:
    """
    Executes a resilient fill action with selector resolution, explicit wait,
    and action retry-with-backoff to handle transient rendering/network jitter.
    """
    backoffs = [0.1, 0.5, 1.0, 2.0]
    last_exc = None

    for attempt, delay in enumerate(backoffs, start=1):
        try:
            # Step 8.1 + 8.4: Resolve locator and check visibility
            locator = await resolve_locator(page, selector, timeout_ms=1000)
            await locator.wait_for(state="visible", timeout=1500)
            await locator.fill(value, timeout=1500)
            log.info("Resilient fill succeeded", extra={"attempt": attempt})
            return
        except Exception as exc:
            last_exc = exc
            log.warning(
                "Fill failed, retrying fill with backoff",
                extra={"attempt": attempt, "delay": delay, "error": str(exc)}
            )
            await asyncio.sleep(delay)

    raise RuntimeError(
        f"Resilient fill failed after {len(backoffs)} retries. "
        f"Last exception: {last_exc}"
    )
