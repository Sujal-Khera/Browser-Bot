"""
browserbot/recorder/convert_codegen.py — Step 2.2: Playwright Codegen Converter.

Converts a Playwright codegen Python script (--target python output) into a
BrowserBot Action Log JSON file that validates against
docs/schemas/action_log_schema.json.

DESIGN
------
Playwright codegen produces a synchronous Python script with statements like:

    page.goto('https://example.com')
    page.get_by_label('Fake order code').fill('NBC-2026-8F3K2Q')
    page.get_by_role('button', name='Show fake timeline').click()
    page.locator('li.status-card h3').inner_text()
    page.wait_for_selector('li.status-card')

The converter works by:

1. Reading the raw script text line-by-line.
2. Applying regex patterns (one per known action type) to extract the
   action, selector/URL, value, and any modifiers.
3. Building the corresponding BrowserBot Step data class for each matched line.
4. Assigning sequential step_index values and monotonically increasing
   timestamp_offset values (estimated from line position — codegen does not
   emit timestamps).
5. Assembling a complete ActionLog and validating it against the schema.

WHY REGEX RATHER THAN AST PARSING
-----------------------------------
- Playwright codegen output follows highly predictable, templated line formats.
  Every action is a single-line method call on `page` or a chained locator.
- AST parsing would handle multi-line expressions correctly but adds significant
  complexity (need to flatten chained attribute access, handle arbitrary
  nesting). The regex approach handles all codegen output patterns observed
  in Playwright 1.61 with far less code.
- Lines that do not match any known pattern are logged as warnings and skipped
  rather than causing a parse failure — this makes the converter resilient to
  minor codegen format changes.

TIMESTAMP ESTIMATION
--------------------
Playwright codegen does not record wall-clock timestamps. The converter
assigns estimated offsets by incrementing a counter (0.5s per step) so the
Action Log has non-negative, strictly increasing timestamp_offset values.
This is acceptable for Phase 2 — the Validator and Pattern Extractor use
the offset for ordering, not for timing-critical replay.

SELECTOR STRATEGY INFERENCE
-----------------------------
The converter inspects the locator chain to infer the `strategy` field:
  - get_by_label(...)           -> "label"
  - get_by_role(...)            -> "role"
  - get_by_placeholder(...)     -> "placeholder"
  - get_by_text(...)            -> "text"
  - get_by_test_id(...)         -> "test_id"
  - locator('css_selector')     -> "css"
  - locator('/xpath')           -> "xpath"
  - filter(has_text=...) chain  -> "css" (composite, treated as css)
"""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from browserbot import __version__
from browserbot.logging import get_logger
from browserbot.models.action_log import (
    ActionLog,
    ActionLogValidator,
    ClickStep,
    ExtractTextStep,
    FillStep,
    GotoStep,
    HoverStep,
    PressKeyStep,
    ScreenshotStep,
    ScrollStep,
    SelectorInfo,
    SessionMetadata,
    WaitStep,
)

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Timestamp step increment (seconds) — used when no real timing is available
# ---------------------------------------------------------------------------

_TIMESTAMP_STEP: float = 0.5


# ---------------------------------------------------------------------------
# Selector extraction helpers
# ---------------------------------------------------------------------------

def _infer_strategy(locator_chain: str) -> tuple[str, dict[str, str | None]]:
    """
    Infer the SelectorInfo strategy and extra kwargs from a locator chain string.

    Args:
        locator_chain: The full locator expression, e.g.
                       ``get_by_role('button', name='Submit')``

    Returns:
        Tuple of (strategy_string, extra_kwargs) where extra_kwargs may contain
        ``aria_role`` and ``aria_name`` for role-based locators.
    """
    extras: dict[str, str | None] = {}

    if "get_by_label" in locator_chain:
        return "label", extras
    if "get_by_placeholder" in locator_chain:
        return "placeholder", extras
    if "get_by_test_id" in locator_chain:
        return "test_id", extras
    if "get_by_text" in locator_chain:
        return "text", extras
    if "get_by_role" in locator_chain:
        # Extract role and name if present
        role_m = re.search(r"get_by_role\(['\"](\w+)['\"]", locator_chain)
        name_m = re.search(r"name=['\"]([^'\"]+)['\"]", locator_chain)
        extras["aria_role"] = role_m.group(1) if role_m else None
        extras["aria_name"] = name_m.group(1) if name_m else None
        return "role", extras

    # Plain locator()
    if locator_chain.startswith("/") or "xpath=" in locator_chain:
        return "xpath", extras
    return "css", extras


def _extract_locator_value(locator_chain: str) -> str:
    """
    Extract the primary selector value string from a locator chain.

    For label/placeholder/text/test_id locators: the quoted argument.
    For role locators: the role name (e.g. "button").
    For css/xpath locators: the selector string itself.
    """
    # get_by_label('Order ID') -> 'Order ID'
    for prefix in ("get_by_label", "get_by_placeholder", "get_by_text", "get_by_test_id"):
        m = re.search(rf"{prefix}\(['\"]([^'\"]+)['\"]", locator_chain)
        if m:
            return m.group(1)

    # get_by_role('button', name='Submit') -> 'button:Submit'
    if "get_by_role" in locator_chain:
        role_m = re.search(r"get_by_role\(['\"](\w+)['\"]", locator_chain)
        name_m = re.search(r"name=['\"]([^'\"]+)['\"]", locator_chain)
        role = role_m.group(1) if role_m else "unknown"
        name = name_m.group(1) if name_m else ""
        return f"{role}:{name}" if name else role

    # locator('css selector') -> 'css selector'
    m = re.search(r"locator\(['\"]([^'\"]+)['\"]", locator_chain)
    if m:
        return m.group(1)

    # filter(has_text='X') chain — return full chain as value
    return locator_chain.strip()


def _build_selector(locator_chain: str) -> SelectorInfo:
    """Build a SelectorInfo from a raw locator chain string."""
    strategy, extras = _infer_strategy(locator_chain)
    value = _extract_locator_value(locator_chain)
    return SelectorInfo(value=value, strategy=strategy, **extras)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Line patterns — matched in order; first match wins
# ---------------------------------------------------------------------------

@dataclass
class _ParsedLine:
    """Result of matching a single codegen script line."""
    kind: str                   # "goto" | "fill" | "click" | ... | "skip" | "unknown"
    kwargs: dict[str, Any] = field(default_factory=dict)


def _parse_line(line: str) -> _ParsedLine:
    """
    Parse a single line of Playwright codegen output.

    Returns a _ParsedLine with kind="skip" for infrastructure lines
    (imports, browser setup, context creation) and kind="unknown" for
    unrecognised page actions (caller logs a warning and skips).
    """
    stripped = line.strip()

    # ---- Lines to skip silently ----
    skip_prefixes = (
        "from playwright",
        "import ",
        "def run(",
        "browser = ",
        "context = ",
        "page = context",
        "page = browser",
        "context.close()",
        "browser.close()",
        "with sync_playwright",
        "    run(playwright)",
        "#",
        '"""',
        "'''",
        "async def",
        "await asyncio",
    )
    if not stripped or any(stripped.startswith(p) for p in skip_prefixes):
        return _ParsedLine(kind="skip")

    # Must be a page action to be interesting
    if "page." not in stripped and not stripped.startswith("page."):
        return _ParsedLine(kind="skip")

    # ---- goto ----
    m = re.match(r"page\.goto\(['\"]([^'\"]+)['\"]", stripped)
    if m:
        return _ParsedLine(kind="goto", kwargs={"url": m.group(1)})

    # ---- fill (chained locator + fill) ----
    # Handles: page.get_by_label('X').fill('value')
    #          page.locator('sel').fill('value')
    #          page.locator('...').filter(...).get_by_role('textbox').fill('val')
    m = re.match(r"(page\..+?)\.fill\(['\"]([^'\"]*)['\"]", stripped)
    if m:
        chain = m.group(1)
        value = m.group(2)
        return _ParsedLine(kind="fill", kwargs={"chain": chain, "value": value})

    # ---- click (chained locator + click) ----
    m = re.match(r"(page\..+?)\.click\(\)", stripped)
    if m:
        chain = m.group(1)
        return _ParsedLine(kind="click", kwargs={"chain": chain})

    # ---- dblclick ----
    m = re.match(r"(page\..+?)\.dblclick\(\)", stripped)
    if m:
        chain = m.group(1)
        return _ParsedLine(kind="click", kwargs={"chain": chain, "click_count": 2})

    # ---- check / uncheck ----
    m = re.match(r"(page\..+?)\.check\(\)", stripped)
    if m:
        return _ParsedLine(kind="check", kwargs={"chain": m.group(1), "checked": True})
    m = re.match(r"(page\..+?)\.uncheck\(\)", stripped)
    if m:
        return _ParsedLine(kind="check", kwargs={"chain": m.group(1), "checked": False})

    # ---- hover ----
    m = re.match(r"(page\..+?)\.hover\(\)", stripped)
    if m:
        return _ParsedLine(kind="hover", kwargs={"chain": m.group(1)})

    # ---- select_option ----
    m = re.match(r"(page\..+?)\.select_option\(['\"]([^'\"]+)['\"]", stripped)
    if m:
        return _ParsedLine(kind="select", kwargs={"chain": m.group(1), "option_value": m.group(2)})

    # ---- press (keyboard key) ----
    m = re.match(r"(page\..+?)\.press\(['\"]([^'\"]+)['\"]", stripped)
    if m:
        return _ParsedLine(kind="press_key", kwargs={"chain": m.group(1), "key": m.group(2)})

    # ---- wait_for_selector ----
    m = re.match(r"page\.wait_for_selector\(['\"]([^'\"]+)['\"]", stripped)
    if m:
        return _ParsedLine(kind="wait_selector", kwargs={"selector": m.group(1)})

    # ---- wait_for_load_state ----
    m = re.match(r"page\.wait_for_load_state\(['\"]([^'\"]+)['\"]", stripped)
    if m:
        return _ParsedLine(kind="wait_network", kwargs={"state": m.group(1)})
    if "page.wait_for_load_state()" in stripped:
        return _ParsedLine(kind="wait_network", kwargs={"state": "load"})

    # ---- inner_text / text_content (treat as extract_text) ----
    m = re.match(r"(page\..+?)\.inner_text\(\)", stripped)
    if m:
        return _ParsedLine(kind="extract_text", kwargs={"chain": m.group(1)})
    m = re.match(r"(page\..+?)\.text_content\(\)", stripped)
    if m:
        return _ParsedLine(kind="extract_text", kwargs={"chain": m.group(1)})

    # ---- screenshot ----
    m = re.match(r"page\.screenshot\(.*path=['\"]([^'\"]+)['\"]", stripped)
    if m:
        return _ParsedLine(kind="screenshot", kwargs={"filename": m.group(1)})

    # ---- scroll ----
    if "page.mouse.wheel(" in stripped:
        m = re.search(r"page\.mouse\.wheel\(([^,]+),\s*([^)]+)\)", stripped)
        if m:
            return _ParsedLine(kind="scroll", kwargs={
                "delta_x": int(float(m.group(1))),
                "delta_y": int(float(m.group(2))),
            })

    # ---- Everything else that starts with page. — log as unknown ----
    return _ParsedLine(kind="unknown", kwargs={"raw": stripped})


# ---------------------------------------------------------------------------
# Strip "page." prefix from chain for selector extraction
# ---------------------------------------------------------------------------

def _chain_to_locator(chain: str) -> str:
    """Remove the leading 'page.' from a locator chain string."""
    if chain.startswith("page."):
        return chain[len("page."):]
    return chain


# ---------------------------------------------------------------------------
# Converter — main public function
# ---------------------------------------------------------------------------


def convert_codegen_script(
    script_text: str,
    *,
    site: str,
    start_url: str | None = None,
    session_id: str | None = None,
    recorded_at: str | None = None,
    workflow_hint: str | None = None,
) -> ActionLog:
    """
    Convert a Playwright codegen Python script into a BrowserBot ActionLog.

    Args:
        script_text:    The raw text of the codegen-generated Python script.
        site:           Hostname of the target website (e.g. "nobuycart.com").
        start_url:      URL of the first page navigated to (optional, inferred
                        from the first goto step if absent).
        session_id:     Unique session identifier.  Auto-generated if absent.
        recorded_at:    ISO 8601 recording timestamp.  Defaults to now (UTC).
        workflow_hint:  Human-readable description of the workflow.

    Returns:
        A validated :class:`ActionLog` instance.

    Raises:
        ValueError: If the converted log fails schema validation.
    """
    if session_id is None:
        now = datetime.now(tz=timezone.utc)
        session_id = f"session_{now.strftime('%Y%m%dT%H%M%S')}"

    if recorded_at is None:
        recorded_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    steps = []
    step_index = 0
    timestamp = 0.0
    inferred_start_url: str | None = start_url

    for line_no, raw_line in enumerate(script_text.splitlines(), start=1):
        parsed = _parse_line(raw_line)

        if parsed.kind == "skip":
            continue

        if parsed.kind == "unknown":
            log.warning(
                "Unrecognised codegen line — skipped",
                extra={"line_no": line_no, "raw": parsed.kwargs.get("raw", "")},
            )
            continue

        base = dict(step_index=step_index, timestamp_offset=round(timestamp, 3))

        if parsed.kind == "goto":
            url = parsed.kwargs["url"]
            if inferred_start_url is None:
                inferred_start_url = url
            step = GotoStep(**base, url=url, wait_until="networkidle")

        elif parsed.kind == "fill":
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = FillStep(
                **base,
                selector=selector,
                value=parsed.kwargs["value"],
                is_sensitive=False,  # PII scrubbing is Step 2.4, not implemented here
            )

        elif parsed.kind == "click":
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = ClickStep(
                **base,
                selector=selector,
                click_count=parsed.kwargs.get("click_count", 1),
            )

        elif parsed.kind == "check":
            from browserbot.models.action_log import CheckStep
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = CheckStep(**base, selector=selector, checked=parsed.kwargs["checked"])

        elif parsed.kind == "hover":
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = HoverStep(**base, selector=selector)

        elif parsed.kind == "select":
            from browserbot.models.action_log import SelectStep
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = SelectStep(
                **base,
                selector=selector,
                option_value=parsed.kwargs["option_value"],
            )

        elif parsed.kind == "press_key":
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = PressKeyStep(**base, selector=selector, key=parsed.kwargs["key"])

        elif parsed.kind == "wait_selector":
            sel_str = parsed.kwargs["selector"]
            step = WaitStep(
                **base,
                wait_for="selector",
                selector=SelectorInfo(value=sel_str, strategy="css"),
                state="visible",
            )

        elif parsed.kind == "wait_network":
            state_map = {
                "load": "network_idle",
                "domcontentloaded": "network_idle",
                "networkidle": "network_idle",
            }
            step = WaitStep(
                **base,
                wait_for=state_map.get(parsed.kwargs["state"], "network_idle"),
            )

        elif parsed.kind == "extract_text":
            chain = _chain_to_locator(parsed.kwargs["chain"])
            selector = _build_selector(chain)
            step = ExtractTextStep(
                **base,
                selector=selector,
                extracted_text="",   # Not available at convert time — filled during replay
                output_variable=None,
            )

        elif parsed.kind == "screenshot":
            step = ScreenshotStep(**base, filename=parsed.kwargs["filename"])

        elif parsed.kind == "scroll":
            step = ScrollStep(
                **base,
                delta_x=parsed.kwargs.get("delta_x"),
                delta_y=parsed.kwargs.get("delta_y"),
            )

        else:
            continue

        steps.append(step)
        step_index += 1
        timestamp += _TIMESTAMP_STEP

    if not steps:
        raise ValueError(
            "Converter produced zero steps — the script may not contain any "
            "recognised page actions, or only contains browser setup code."
        )

    # Infer site from start_url if not supplied
    if not site and inferred_start_url:
        parsed_url = urllib.parse.urlparse(inferred_start_url)
        site = parsed_url.netloc or "unknown"

    metadata = SessionMetadata(
        session_id=session_id,
        site=site,
        start_url=inferred_start_url,
        recorded_at=recorded_at,
        browserbot_version=__version__,
        duration_seconds=round(timestamp - _TIMESTAMP_STEP, 3),
        step_count=len(steps),
        workflow_hint=workflow_hint,
    )

    action_log = ActionLog(
        schema_version="1.0",
        metadata=metadata,
        steps=steps,  # type: ignore[arg-type]
    )

    # Validate against JSON Schema before returning
    validator = ActionLogValidator()
    validator.assert_valid(
        action_log.model_dump(mode="json", exclude_none=True),
        label=session_id,
    )

    log.info(
        "Codegen conversion complete",
        extra={
            "session_id": session_id,
            "steps": len(steps),
            "site": site,
        },
    )
    return action_log


def convert_codegen_file(
    script_path: str | Path,
    *,
    site: str = "",
    start_url: str | None = None,
    session_id: str | None = None,
    recorded_at: str | None = None,
    workflow_hint: str | None = None,
) -> ActionLog:
    """
    Convenience wrapper: read a codegen script file and convert it.

    Args:
        script_path: Path to the codegen-generated Python script file.
        site:        Hostname override (inferred from first goto if blank).
        (other args same as :func:`convert_codegen_script`)

    Returns:
        A validated :class:`ActionLog` instance.
    """
    text = Path(script_path).read_text(encoding="utf-8")
    log.info("Reading codegen script", extra={"path": str(script_path)})
    return convert_codegen_script(
        text,
        site=site,
        start_url=start_url,
        session_id=session_id,
        recorded_at=recorded_at,
        workflow_hint=workflow_hint,
    )
