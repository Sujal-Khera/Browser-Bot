"""Validation script for Step 2.2 and 2.3 — run from repo root."""
import json
import sys
from pathlib import Path

# Ensure repo root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from browserbot.recorder.convert_codegen import convert_codegen_script
from browserbot.models import ActionLogValidator

CODEGEN_SCRIPT = (
    "from playwright.sync_api import Playwright, sync_playwright, expect\n"
    "\n"
    "\n"
    "def run(playwright: Playwright) -> None:\n"
    "    browser = playwright.chromium.launch(headless=False)\n"
    "    context = browser.new_context()\n"
    "    page = context.new_page()\n"
    "    page.goto('https://nobuycart.com/tracking/')\n"
    "    page.get_by_label('Fake order code').click()\n"
    "    page.get_by_label('Fake order code').fill('NBC-2026-8F3K2Q')\n"
    "    page.get_by_role('button', name='Show fake timeline').click()\n"
    "    page.wait_for_selector('li.status-card')\n"
    "    page.locator('div.surface.overflow-hidden h2').inner_text()\n"
    "    page.locator('li.status-card h3').inner_text()\n"
    "    context.close()\n"
    "    browser.close()\n"
    "\n"
    "\n"
    "with sync_playwright() as playwright:\n"
    "    run(playwright)\n"
)

# --- Test 1: Converter produces an ActionLog ---
action_log = convert_codegen_script(
    CODEGEN_SCRIPT,
    site="nobuycart.com",
    session_id="session_20260715T200000",
    recorded_at="2026-07-15T20:00:00Z",
    workflow_hint="NoBuyCart fake order tracking",
)

print("[PASS] Converter produced ActionLog")
print(f"       Steps: {len(action_log.steps)}")
print(f"       Actions: {[s.action for s in action_log.steps]}")

# --- Test 2: JSON Schema validation ---
validator = ActionLogValidator()
data = action_log.model_dump(mode="json", exclude_none=True)
errors = validator.validate(data)
if errors:
    print("[FAIL] JSON Schema errors:")
    for e in errors:
        print(" ", e)
    sys.exit(1)
else:
    print("[PASS] Validates against JSON Schema (Draft 2020-12)")

# --- Test 3: Step ordering ---
for i, step in enumerate(action_log.steps):
    assert step.step_index == i, f"step_index mismatch at {i}: got {step.step_index}"
print("[PASS] Step ordering preserved (step_index == position)")

# --- Test 4: Selector strategy inference ---
fill_steps = [s for s in action_log.steps if s.action == "fill"]
assert fill_steps, "No fill steps found"
assert fill_steps[0].selector.strategy == "label", (
    f"Expected label, got {fill_steps[0].selector.strategy!r}"
)
print(f"[PASS] Fill selector strategy=label, value={fill_steps[0].selector.value!r}")

click_steps = [s for s in action_log.steps if s.action == "click"]
# First click is the get_by_label().click() — strategy=label
# Second click is get_by_role() — strategy=role
role_clicks = [s for s in click_steps if s.selector.strategy == "role"]
assert role_clicks, "No role-based click found"
assert role_clicks[0].selector.aria_role == "button"
print(f"[PASS] Button click strategy=role, aria_role=button, aria_name={role_clicks[0].selector.aria_name!r}")

# --- Test 5: session JSON round-trip ---
tmp_path = Path("workflows/sessions/test_validation.json")
tmp_path.parent.mkdir(parents=True, exist_ok=True)
action_log.to_file(tmp_path)
from browserbot.models import ActionLog
loaded = ActionLog.from_file(tmp_path)
assert loaded.schema_version == "1.0"
assert loaded.metadata.session_id == "session_20260715T200000"
assert len(loaded.steps) == len(action_log.steps)
tmp_path.unlink()
print("[PASS] ActionLog round-trips through JSON file correctly")

# --- Test 6: Verify step 2.3 imports ---
from browserbot.recorder.codegen_runner import run_recording_session  # noqa: F401
print("[PASS] codegen_runner.run_recording_session importable")

from browserbot.recorder import convert_codegen_script, convert_codegen_file, run_recording_session  # noqa: F401
print("[PASS] browserbot.recorder public API importable")

print()
print("[PASS] All Step 2.2 + 2.3 validation checks passed.")
