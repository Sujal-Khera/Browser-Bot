# run_04 — Phase 2 Step 2.4: PII / Secret Scrubbing

## Summary

Step 2.4 is complete. The security boundary for BrowserBot is now implemented.

**Deliverable:** A standalone, independent `Scrubber` module that:
- Detects sensitive `FillStep` values using keyword matching (26 built-in
  keywords) + field_label matching + a configurable extra_selectors set
- Replaces sensitive values with stable `__SECRET_N__` placeholders before
  anything reaches disk
- Preserves action structure (steps are not deleted)
- Re-uses the same placeholder for repeated identical values within a session
- Is wired into the codegen runner pipeline between `convert_codegen_file()`
  and `action_log.to_file()`

The complete Phase 2 recording pipeline is now:

```
playwright codegen  →  raw_script.py  →  convert_codegen_file()
                    →  scrub()         →  action_log.to_file()
                    →  session_<ts>.json  (no plaintext secrets ever written)
```

**Tests:** 12 automated tests all passing.

---

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `browserbot/recorder/scrubber.py` | Created | Step 2.4: Scrubber class + `scrub()` function |
| `browserbot/recorder/codegen_runner.py` | Modified | Wired `scrub()` between convert and disk write |
| `browserbot/recorder/__init__.py` | Modified | Exports `scrub`, `Scrubber`, `ScrubResult` |
| `browserbot/recorder/convert_codegen.py` | Modified | Updated stale Step 2.4 TODO comment |
| `tests/test_scrubber.py` | Created | 12 automated tests for the scrubber |

---

## Validation Results

### Automated Tests

```
12 passed in 0.32s
```

| Test | Result |
|------|--------|
| `test_password_field_is_redacted` | PASS |
| `test_multiple_distinct_passwords_get_distinct_placeholders` | PASS |
| `test_repeated_secret_reuses_same_placeholder` | PASS |
| `test_username_not_redacted` | PASS |
| `test_normal_fields_preserved` | PASS |
| `test_configurable_extra_selectors` | PASS |
| `test_mixed_workflow_only_sensitive_steps_touched` | PASS |
| `test_scrubbed_session_validates_against_schema` | PASS |
| `test_field_label_keyword_triggers_redaction` | PASS |
| `test_scrub_result_metadata` | PASS |
| `test_token_field_redacted` | PASS |
| `test_scrubber_does_not_modify_non_fill_steps` | PASS |

### Regression Checks

| Check | Result |
|-------|--------|
| `scripts/validate_step_2_2.py` (all 6 checks) | **PASS** |
| `scripts/verify_env.py --no-ollama` (6/6) | **PASS** |
| `tests/test_scrubber.py` (12/12) | **PASS** |

### Security Invariants Verified

| Invariant | Verification |
|-----------|-------------|
| No plaintext password reaches disk | `test_password_field_is_redacted` — value is `__SECRET_1__` in the ActionLog before `to_file()` |
| Repeated secrets map to identical placeholders | `test_repeated_secret_reuses_same_placeholder` — two identical passwords → both `__SECRET_1__` |
| Session JSON validates after scrubbing | `test_scrubbed_session_validates_against_schema` — 0 schema errors after scrub |
| Existing recorder functionality unchanged | Step 2.2 validation script still passes; `--demo` smoke-test intact |

---

## Security Design

### Placeholder Strategy

Placeholders use the format `__SECRET_N__` where N is a session-scoped integer
counter starting at 1.

The counter increments per **unique plaintext value**, not per step:
- Different values → different placeholders (`__SECRET_1__`, `__SECRET_2__`, ...)
- Same value appearing multiple times → same placeholder (`__SECRET_1__` each time)

This mapping is maintained in a `value_to_placeholder: dict[str, str]` that
lives ONLY in the `Scrubber.scrub()` call stack — it is never serialised,
never logged at INFO level, and never written to any file.

### Why Values are Replaced Instead of Removed

Removing a FillStep entirely would break three downstream phases:

1. **Validator (Phase 5)**: replay would skip the field → form submits empty
   → test fails (wrong behavior, not a security failure, but functionally broken)
2. **Code Generator (Phase 4)**: generated tool code would be missing the
   fill step → the tool would not work when run live
3. **Schema integrity**: removing a step creates step_index gaps, breaking
   the `ActionLog.validate_step_indices` invariant

Replacing with `__SECRET_N__` preserves the structure. When the generated
tool runs live (Phase 6+), the MCP tool receives the real value as a parameter
and fills it in at runtime — the placeholder serves as the parameter slot
name until the Code Generator assigns it a proper variable name.

### Future Extension Points

| Extension | How to add |
|-----------|-----------|
| Add a keyword | Append to `DEFAULT_SENSITIVE_KEYWORDS` in `scrubber.py` — all call sites pick it up automatically |
| Per-site keyword set | Subclass `Scrubber` and override `_is_sensitive()`, or pass `extra_selectors` per site |
| Env-var configuration | `BROWSERBOT_SENSITIVE_SELECTORS=input#my_field,My Label` — already supported |
| Regex-based detection | Replace the keyword `in` check with a compiled regex in `_is_sensitive()` |
| Audit trail | Extend `ScrubResult.step_indices` to also record the `selector.value` and `placeholder` — never the plaintext value |
| Credit card / SSN | Add `"card"`, `"cvv"`, `"ssn"`, `"social"` to `DEFAULT_SENSITIVE_KEYWORDS` |

---

## Test Coverage

| Requirement (from scope) | Test |
|--------------------------|------|
| password field | `test_password_field_is_redacted` |
| multiple passwords | `test_multiple_distinct_passwords_get_distinct_placeholders` |
| repeated secret reuse | `test_repeated_secret_reuses_same_placeholder` |
| username not redacted | `test_username_not_redacted` |
| normal form fields preserved | `test_normal_fields_preserved` |
| configurable sensitive field | `test_configurable_extra_selectors` |
| mixed workflow | `test_mixed_workflow_only_sensitive_steps_touched` |
| schema validates after scrub | `test_scrubbed_session_validates_against_schema` |
| field_label detection | `test_field_label_keyword_triggers_redaction` *(bonus)* |
| ScrubResult metadata | `test_scrub_result_metadata` *(bonus)* |
| token field | `test_token_field_redacted` *(bonus)* |
| non-fill steps untouched | `test_scrubber_does_not_modify_non_fill_steps` *(bonus)* |

---

## Remaining Work

Phase 2 is now **complete**. All four steps are done:

| Step | Description | Status |
|------|-------------|--------|
| 2.1 | Define Action Log JSON Schema | Done (run_02) |
| 2.2 | Playwright Codegen converter | Done (run_03) |
| 2.3 | Minimal Recording CLI | Done (run_03) |
| 2.4 | PII / Secret scrubbing | **Done (this batch)** |

---

## Next Batch

**Phase 3 — Step 3.1: Pattern Extraction Agent (LLM Agent 1)**

From the execution plan, Phase 3's objective is:

> Reliably identify which actions in the Action Log are workflow-essential
> (the ordered sequence a tool must reproduce) vs. exploratory (clicks on
> wrong elements, accidental navigation, backtracking).

Step 3.1: Design the Pattern Extractor's input/output contract and prompt.
The extractor takes a validated, scrubbed ActionLog and produces a structured
workflow representation that the Code Generator (Phase 4) can consume.

Do NOT begin Phase 3 until explicitly requested.

---

*Generated by run_04 — 2026-07-16*
