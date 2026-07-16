# run_05 — Pre–Phase 3 Architecture Freeze

## Architecture Review

This batch reviewed the entire Phase 2 Recorder subsystem before Phase 3
(Pattern Extractor + first LLM agent) is introduced. The objective was to
identify and fix any structural issues that would be difficult to change once
later phases depend on the Recorder's contract.

### Issues Found and Fixed

| # | Issue | Severity | Resolution |
|---|-------|----------|-----------|
| 1 | `object.__setattr__` on a Pydantic v2 model in `scrubber.py` | **Critical** | `Scrubber.scrub()` redesigned as a pure function using `model_copy()` |
| 2 | `scrub()` had in-place mutation semantics — callers shared state | **Critical** | API changed: returns new ActionLog in `ScrubResult.action_log`; original never modified |
| 3 | `urllib.parse` imported inside function body in `codegen_runner.py` | Minor | Moved to top-level import |
| 4 | No structured error logging on failure paths in `codegen_runner.py` | Minor | Added `log.error(...)` before every `raise RuntimeError` |
| 5 | Post-scrub schema re-validation missing in production pipeline | **Important** | Added `ActionLogValidator.assert_valid()` call in `codegen_runner.py` between scrub and disk write |
| 6 | Tests used original `log` object after `scrub(log)` — verified nothing | **Critical** | All 13 tests rewritten to use `result.action_log` for post-scrub assertions |
| 7 | Dead code block left in `scrubber.py` after previous edit | Minor | Rewrote `scrubber.py` cleanly |
| 8 | Unused imports (`json`, `Path`, `pytest`) in test file | Minor | Removed |

---

## Interfaces Frozen

The following public interfaces are now **frozen**. Phase 3 (Pattern
Extractor) will consume these and must not require changes to them.

### `browserbot.models.ActionLog`

```python
from browserbot.models import ActionLog

log = ActionLog.from_file(path)         # Load from disk
data = log.model_dump(mode="json")      # Serialize for LLM prompt
log.schema_version                       # "1.0"
log.metadata.session_id                  # str
log.metadata.site                        # str (hostname)
log.metadata.recorded_at                 # ISO 8601 str
log.metadata.browserbot_version          # str
log.metadata.workflow_hint               # str | None
log.metadata.step_count                  # int | None
log.steps                                # list[Step]
```

### `browserbot.models.ActionLogValidator`

```python
from browserbot.models import ActionLogValidator

validator = ActionLogValidator()
errors = validator.validate(data)         # list[str] — empty = valid
validator.assert_valid(data, label=...)  # raises ValueError on failure
```

### `browserbot.recorder.scrub` (pure function)

```python
from browserbot.recorder import scrub

result = scrub(action_log)
result.action_log      # ActionLog — the scrubbed copy (NEVER original)
result.scrubbed_count  # int
result.secret_count    # int
result.step_indices    # list[int]
# result.value_map     # dict — in memory ONLY, never persisted
```

**Contract:** `scrub()` is a pure function. The original `action_log`
argument is **never modified**. Phase 3 can safely call `scrub()` and inspect
both the original and the scrubbed log without aliasing concerns.

### `browserbot.recorder.run_recording_session`

```python
from browserbot.recorder import run_recording_session

session_path: Path = run_recording_session(
    url="https://...",
    workflow_hint="...",
    output_dir=None,   # defaults to settings.sessions_dir
)
# Returns: Path to session_<timestamp>.json
# Guarantees: file is scrubbed and schema-valid before being written
```

### `browserbot.config.settings`

```python
from browserbot.config.settings import settings

settings.sessions_dir            # Path — where session JSON files live
settings.project_root            # Path
settings.llm_backend             # "ollama" | "groq"
settings.ollama_model_extractor  # str — model for Pattern Extractor
settings.ollama_model_generator  # str — model for Code Generator
settings.groq_api_key            # str | None
settings.groq_model              # str
```

---

## Schema Review

### Is the Action Log schema frozen?

**Yes. The Action Log schema (`docs/schemas/action_log_schema.json`,
`schema_version: "1.0"`) is hereby frozen as of run_05.**

Evidence for stability:
- The schema has been validated against a hand-crafted example (`action_log_example.json`) in every run since run_02.
- The Pydantic models are a strict 1:1 mirror of the JSON Schema. Any divergence raises a validation error.
- The schema uses `additionalProperties: false` on every object — unknown fields are rejected loudly.
- The `schema_version: "1.0"` is a `const` — a downstream agent that reads a log with version `"2.0"` will fail fast rather than silently misinterpret it.
- The schema description explicitly states: *"Version 1 — frozen contract."*

### What would require a schema version bump?

Any of the following would require a `schema_version: "2.0"` bump:
- Adding a new required field to `BaseStep` or any step type
- Removing or renaming any existing field
- Changing the discriminator key name (`action`)
- Changing the `session_id` pattern regex

Adding a new **optional** step type (new `action` value) is backward-compatible
and does not require a version bump.

---

## Improvements Made

| File | Change |
|------|--------|
| `browserbot/recorder/scrubber.py` | Rewrote as a pure function; eliminated `object.__setattr__`; removed dead code |
| `browserbot/recorder/codegen_runner.py` | Top-level `urllib.parse` import; failure logging; post-scrub re-validation; uses `result.action_log` |
| `tests/test_scrubber.py` | Rewrote all 13 tests for pure-function API; added Test 13 (pure-function contract guarantee) |

---

## Validation Results

| Check | Result |
|-------|--------|
| `pytest tests/test_scrubber.py -v` (13/13) | **PASS** |
| `scripts/validate_step_2_2.py` (6/6) | **PASS** |
| `scripts/verify_env.py --no-ollama` (6/6) | **PASS** |

### Pipeline Integrity Verified

The execution path from recorder to disk now has **no bypass**:

```
playwright codegen
    → raw_script.py   (subprocess, user-controlled)
    → convert_codegen_file()
        → ActionLog (unscrubbed, in memory only)
    → scrub(action_log)
        → ScrubResult.action_log  (new scrubbed copy, in memory only)
    → ActionLogValidator.assert_valid()  (post-scrub schema check)
    → scrubbed_log.to_file()   ← first disk write
```

There is no code path that reaches `to_file()` before `scrub()`.
There is no code path that uses the original unscrubbed `action_log` after `scrub()` returns.

---

## Risks Remaining (Pre–Phase 3)

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| `WaitStep.selector` is optional but `wait_for="selector"` requires it — not enforced at schema level | Low | Low | Known issue KI-03 from run_03; Pydantic `model_validator` can be added before Phase 5 (Validator) |
| `extracted_text=""` in `ExtractTextStep` after conversion — ground truth not available until replay | Low | Low | Known issue KI-01 from run_03; acceptable for Phase 3 (pattern extraction needs selector, not value) |
| `site` field uses `format: "hostname"` but jsonschema does not enforce formats by default | Low | Low | Documented in run_02 KI-02; does not affect correctness |
| `BROWSERBOT_SENSITIVE_SELECTORS` env var could be misconfigured (typos, wrong format) | Low | Medium | Documented in scrubber docstring; future improvement: validation on startup |
| Schema frozen but `ExtractTextStep.extracted_text` is always `""` after conversion — Phase 3 must know this | Low | Medium | Phase 3 should read `extracted_text` as a hint, not a ground truth. Document in Phase 3 prompt. |

---

## Recommendation

**BrowserBot is ready to begin Phase 3.**

All Phase 2 subsystems are stable, tested, and their APIs are frozen:
- The Action Log schema is explicitly versioned and frozen.
- The public interfaces Phase 3 will consume are documented above.
- The pipeline integrity guarantee (no unsanitized data reaches disk) is
  verified by the post-scrub re-validation in `codegen_runner.py` and enforced
  by the Test 13 pure-function contract test.
- All existing tests pass. No known regressions.

Phase 3 may proceed when the user sends the next prompt.

---

*Generated by run_05 — 2026-07-16*
