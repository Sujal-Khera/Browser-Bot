# run_03 — Phase 2 Steps 2.2 + 2.3: Browser Recorder

## Summary

Two Phase 2 execution-plan steps completed:

- **Step 2.2** — Playwright Codegen Converter: a line-by-line regex parser
  (`browserbot/recorder/convert_codegen.py`) that converts Playwright codegen
  Python output into a BrowserBot Action Log JSON file conforming to the v1
  schema.

- **Step 2.3** — Minimal Recording CLI: `python -m browserbot.recorder start [URL]`
  shells out to `playwright codegen`, waits for the user to close the browser,
  then automatically invokes the converter and writes
  `session_<timestamp>.json` to `workflows/sessions/`.

The existing `--demo` smoke-test in the recorder entry point was preserved and
continues to pass.

---

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `browserbot/recorder/convert_codegen.py` | Created | Step 2.2: codegen → ActionLog converter |
| `browserbot/recorder/codegen_runner.py` | Created | Step 2.3: subprocess wrapper + pipeline |
| `browserbot/recorder/__main__.py` | Replaced | Added `start` subcommand; kept `--demo` |
| `browserbot/recorder/__init__.py` | Replaced | Exports Step 2.2/2.3 public API |
| `browserbot/config/settings.py` | Modified | Added `sessions_dir` property |
| `.gitignore` | Modified | Added `workflows/sessions/` and `*_raw.py` |
| `scripts/validate_step_2_2.py` | Created | Validation script (6 checks) |

---

## Validation Results

| # | Check | Command / Method | Result |
|---|-------|-----------------|--------|
| 1 | Converter imports cleanly | `from browserbot.recorder.convert_codegen import convert_codegen_script` | **PASS** |
| 2 | Converter produces ActionLog from codegen script | `convert_codegen_script(CODEGEN_SCRIPT, ...)` | **PASS** — 7 steps |
| 3 | Action Log validates against JSON Schema | `ActionLogValidator().validate(data)` | **PASS** — 0 errors |
| 4 | step_index ordering preserved | `step.step_index == i` for all steps | **PASS** |
| 5 | Selector strategy inference — label | `fill.selector.strategy == "label"` | **PASS** |
| 6 | Selector strategy inference — role | `click.selector.strategy == "role"` | **PASS** |
| 7 | ActionLog JSON file round-trip | `ActionLog.to_file()` / `ActionLog.from_file()` | **PASS** |
| 8 | CLI `start` subcommand importable | `from browserbot.recorder.codegen_runner import run_recording_session` | **PASS** |
| 9 | CLI help renders correctly | `python -m browserbot.recorder start --help` | **PASS** |
| 10 | `--demo` smoke-test still passes | `python -m browserbot.recorder --demo` | **PASS** — `'Example Domain'` |
| 11 | Environment verification unchanged | `python scripts/verify_env.py --no-ollama` | **PASS** — 6/6 |

Validated action types extracted from NoBuyCart codegen script:
`['goto', 'click', 'fill', 'click', 'wait', 'extract_text', 'extract_text']`

---

## Converter Design

### How Playwright Output is Parsed

The converter (`convert_codegen.py`) processes the codegen script **line-by-line**
using a priority-ordered set of regular expression patterns, one per known
action type.

Each line is passed through `_parse_line()`, which:

1. Silently skips infrastructure lines (imports, `browser =`, `context.close()`, etc.)
2. Returns `kind="unknown"` for any `page.*` call that matches no known pattern
   (these are logged as warnings and skipped — not errors)
3. Returns a `_ParsedLine(kind, kwargs)` for recognised actions

The matched `kind` then determines which Pydantic Step model is instantiated:

```
page.goto(url)                      →  GotoStep
page.get_by_label('X').fill('v')    →  FillStep   (strategy=label)
page.get_by_role('btn').click()     →  ClickStep  (strategy=role)
page.locator('sel').click()         →  ClickStep  (strategy=css)
page.get_by_label('X').click()      →  ClickStep  (strategy=label)
page.wait_for_selector('sel')       →  WaitStep   (wait_for=selector)
page.locator('sel').inner_text()    →  ExtractTextStep
page.locator('sel').fill('v')       →  FillStep   (strategy=css)
page.get_by_placeholder('X')...     →  FillStep   (strategy=placeholder)
```

Selector strategy is inferred by `_infer_strategy()` by inspecting the
locator chain string for method names:
- `get_by_label` → `"label"`
- `get_by_role` → `"role"` (+ extracts `aria_role` and `aria_name`)
- `get_by_placeholder` → `"placeholder"`
- `get_by_text` → `"text"`
- `get_by_test_id` → `"test_id"`
- `locator('/xpath')` → `"xpath"`
- `locator('css')` → `"css"` (default)

### Why Regex Rather Than AST Parsing

Playwright codegen produces **highly templated, single-line** method call
statements.  Every action is one line.  Regex handles all observed patterns
with ~100 lines of code.  AST parsing would require:

- Importing `ast`, building a visitor
- Flattening arbitrarily deep chained attribute access
- Handling `Call.func` being an `Attribute` vs `Name`

For the subset of Playwright codegen output (not arbitrary Python), regex is
strictly simpler, equally correct, and far easier to debug and extend.

### Assumptions

1. **One action per line** — Playwright codegen always produces single-line
   statements. Multi-line continuations are not produced by codegen.

2. **Timestamps are estimated** — Codegen does not record wall-clock times.
   `timestamp_offset` is assigned as `step_index * 0.5s`. This is sufficient
   for the Validator (which uses offsets for ordering, not timing-critical
   replay) and the Pattern Extractor (which ignores timestamps entirely).

3. **`extracted_text` is empty at convert time** — `ExtractTextStep` stores
   `extracted_text=""` because codegen does not capture the return value of
   `inner_text()`. The Validator (Phase 5) must replay the step to capture
   the actual value for diff comparison.

4. **No PII scrubbing (Step 2.4 not implemented)** — `FillStep.is_sensitive`
   is always `False`. Step 2.4 will add detection of `type="password"` fields
   and replace values with `__SECRET_N__` before writing to disk.

5. **Site is inferred from first `goto` URL** — If `site` is not supplied to
   the converter, the hostname is extracted from the first `goto` step's URL
   via `urllib.parse.urlparse`.

---

## Remaining Work in Phase 2

| Step | Description | Status |
|------|-------------|--------|
| 2.1 | Define Action Log JSON Schema | **DONE** (run_02) |
| 2.2 | Playwright Codegen converter | **DONE** (this batch) |
| 2.3 | Minimal Recording CLI | **DONE** (this batch) |
| 2.4 | PII / Secret scrubbing at capture time | **NOT STARTED** |

Step 2.4 is the only remaining Phase 2 work.

---

## Known Issues

### KI-01: `ExtractTextStep.extracted_text` is always empty after conversion

Playwright codegen records `page.locator('sel').inner_text()` calls but does
NOT capture the return value in the script (it is a side-effect-free
expression in the codegen output). The converter therefore stores `""` as the
`extracted_text` value.

**Impact:** The Phase 5 Validator cannot diff the extracted text from a
converted session against the ground truth using only the JSON file — it must
replay the step to get the actual value.

**Resolution path:** The Validator (Phase 5) is designed to re-run the
extraction step and compare the result at that point. This is acceptable per
the execution plan: Step 2.2's verification is "diff the auto-generated JSON
log's **replayed** behavior against the ground-truth script's behavior."

### KI-02: Chained filter().get_by_role() locators use "css" strategy

Playwright codegen occasionally produces complex chains like:
```python
page.locator('label').filter(has_text='Fake order code').get_by_role('textbox').fill('value')
```

The converter's `_infer_strategy()` correctly identifies `get_by_role` in
this chain and returns `"role"`. However, `_extract_locator_value()` returns
the role name (e.g., `"textbox"`) rather than the full chain — this loses
the `filter()` context.

**Impact:** The selector value in the Action Log is less specific than the
original for these complex chains. The step is still correctly classified and
actionable.

**Resolution path:** Phase 8 (self-healing selectors) will regenerate selectors
from semantic hints anyway. The current behaviour is acceptable for Phase 2.

---

## Next Batch

**Step 2.4 — PII/Secret Scrubbing at Capture Time**

From the execution plan:

> Before anything is written to disk, redact `password`/`type=password` field
> values and any field explicitly flagged as sensitive, replacing the value with
> a placeholder token (`__SECRET_1__`).

Implementation location: `browserbot/recorder/convert_codegen.py` —
`FillStep` construction in `_parse_line` / the `fill` branch.

The schema model (`FillStep.is_sensitive` + `sensitive_fields_must_be_scrubbed`
validator) is already in place from Step 2.1. Step 2.4 needs only the
detection logic in the converter.

Verification: Record a login flow, confirm the session JSON shows
`__SECRET_1__`, not the plaintext password.

Do NOT begin Phase 3 until Step 2.4 is complete.

---

*Generated by run_03 — 2026-07-15*
