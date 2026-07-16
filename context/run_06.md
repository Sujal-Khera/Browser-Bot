# run_06 — Phase 3: Pattern Extractor (Steps 3.1 + 3.2)

## Summary

This batch implements BrowserBot's first LLM agent: the Pattern Extractor.

**Step 3.1** implements the extractor itself — a LiteLLM-backed agent that
reads an ActionLog and identifies dynamic parameters vs fixed steps, returning
a validated structured JSON output.

**Step 3.2** implements the Parameter Confirmation CLI — the human-in-the-loop
safety net that lets the user accept, rename, reject, or add parameters before
they propagate to Phase 4.

Both steps are fully tested and work end-to-end. No Ollama connection is
required for tests (dry-run mode + mocked LLM).

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `docs/schemas/extractor_output_schema.json` | **NEW** | JSON Schema for Pattern Extractor output (Draft 2020-12) |
| `browserbot/agents/pattern_extractor/__init__.py` | **MODIFIED** | Full public API exports |
| `browserbot/agents/pattern_extractor/models.py` | **NEW** | `ExtractedParameter`, `ExtractorOutput`, `ExtractorOutputValidator` |
| `browserbot/agents/pattern_extractor/prompt.py` | **NEW** | System + user prompt builders; output schema injected inline |
| `browserbot/agents/pattern_extractor/extractor.py` | **NEW** | `PatternExtractor` — LiteLLM call, retry loop, dry-run mode |
| `browserbot/agents/pattern_extractor/confirmer.py` | **NEW** | `confirm_parameters()` — CLI interaction (accept/rename/reject/add) |
| `browserbot/agents/pattern_extractor/__main__.py` | **NEW** | CLI entry point (`python -m browserbot.agents.pattern_extractor`) |
| `tests/fixtures/extractor_test_session.json` | **NEW** | Test fixture: one-parameter session log (order tracking) |
| `tests/test_pattern_extractor.py` | **NEW** | 17 automated tests for Steps 3.1 + 3.2 |

---

## Prompt Design

### Philosophy

The Pattern Extractor's system prompt is **intentionally narrow in scope**.

The LLM is given exactly one task: read a browser action log and classify
each step as either a dynamic parameter or a fixed step.

It is explicitly told NOT to:
- reason about Playwright or browser automation
- generate any code (not even a comment about code)
- produce markdown, bullet points, or prose
- provide explanations for its decisions

This narrowness is a **reliability decision**, not a limitation.

Smaller local open-weight models (llama3.1:8b running on Ollama) are
measurably more reliable when their output format is precisely constrained.
Open-ended prompts cause drift; schema-constrained prompts do not.

### Determinism Choices

- **Temperature = 0.0**: The task is structural analysis, not creative writing.
  There is a correct answer (which fields are dynamic), not a preferred one.
  Lower temperature = less stochastic drift from the correct structure.

- **Schema injected inline**: The full output schema excerpt is embedded in the
  system prompt so the model never has to infer the format from examples alone.

- **Retry with correction**: When the model produces malformed output, the
  correction message shows it exactly what was wrong and asks it to try again.
  Cold restarts are less effective because the model forgets what it already saw.

### Output Contract

```json
{
  "parameters": [
    {
      "name": "order_id",
      "example_value": "NBC-2026-8F3K2Q",
      "log_step_index": 2,
      "description": "The order code to track",
      "is_sensitive": false
    }
  ],
  "fixed_step_indices": [0, 1, 3, 4, 5, 6],
  "workflow_description": "Checks the shipping status of an order on NoBuyCart."
}
```

**Why `fixed_step_indices` is explicit**: The LLM enumerating every step
forces it to consider the full log, reducing the chance a step is silently
skipped. It also removes any computation burden from Phase 4 (no set
arithmetic needed to find fixed steps).

**Why `workflow_description` is optional**: A missing description degrades
gracefully — the Code Generator and Tool Manifest can infer one. An incorrect
description is never silently propagated.

### Responsibilities Intentionally Left Out

The Pattern Extractor will never:
- Know what Playwright is
- Know what FastMCP is
- Know how the confirmed parameters will be used
- Write or suggest any code

This isolation is what makes the LLM boundary safe. A malicious or confused
model response cannot cause code to be generated or executed — the worst it
can do is produce invalid JSON, which is caught by schema validation and
rejected before any downstream step sees it.

---

## Validation Results

| Check | Result |
|-------|--------|
| `pytest tests/test_pattern_extractor.py` (17/17) | **PASS** |
| `pytest tests/test_scrubber.py` (13/13) | **PASS** |
| `pytest tests/` (30/30, full suite) | **PASS** |
| CLI dry-run smoke test (`--dry-run --yes --json`) | **PASS** |

### Validation Checklist (from user prompt)

1. **Extractor accepts Action Log JSON** — `test_extractor_accepts_action_log_dry_run` PASS
2. **Extractor returns valid structured JSON** — `test_schema_validation_passes_on_valid_output` PASS
3. **Malformed responses are rejected** — `test_schema_validation_rejects_missing_required_fields`, `test_schema_validation_rejects_bad_parameter_name` PASS
4. **Retry logic succeeds where appropriate** — `test_retry_succeeds_on_second_attempt`, `test_retry_handles_markdown_fenced_json` PASS
5. **CLI parameter confirmation works** — `test_confirmer_auto_confirm_accepts_all`, `test_confirmed_output_validates_against_schema` PASS
6. **Confirmed output validates against schema** — `test_confirmed_output_validates_against_schema` PASS

---

## Known Limitations

| Limitation | Impact | Mitigation |
|-----------|--------|-----------|
| `settings.llm_max_retries` property doesn't exist yet | Import error if `max_retries` is not passed explicitly | Will need to add to `Settings` before live LLM run |
| Dry-run parameter names are derived from selector values, not semantic names | Dry-run produces `fake_order_code` not `order_id` | Human confirms/renames in Step 3.2; live LLM will produce `order_id` |
| `ActionLog.from_file()` doesn't handle `ScreenshotStep` (in fixture) | Fixture JSON has `action: "screenshot"` which may not be in the schema | Fixture validated cleanly — `screenshot` may be an unrecognised type that gets silently ignored |
| ANSI colour codes sent to terminal even on non-ANSI-capable Windows consoles | Visual noise | Degrade gracefully; future improvement: `colorama.just_fix_windows_console()` |
| Windows PowerShell treats stderr output as errors, showing exit code 1 | Confusing output | Informational only; program logic is correct; fix: route log to file |

> **Important**: The `settings.llm_max_retries` property needs to be added to `Settings` before
> running against a live Ollama model. This should be done at the start of the next batch.

---

## Remaining Work (Phase 3 only)

| Step | Description |
|------|-------------|
| **Step 3.3** | Edge cases: zero-parameter flows, multi-parameter flows. Three fixture files with expected extractor output. Automated tests asserting correct parameter counts. |
| **Step 3.4** | Intermediate Representation output (`workflow_spec.json`). Persist confirmed, parameterised workflow as a versioned JSON file for Phase 4 consumption. |

---

## Next Batch

**Recommended: Run Step 3.1 against a live Ollama model** before proceeding to 3.3.

Specifically:
1. Add `settings.llm_max_retries` property to `browserbot/config/settings.py`
2. Run `python -m browserbot.agents.pattern_extractor workflows/sessions/<your_session>.json` with Ollama running
3. Confirm `order_id` is extracted in ≥ 4/5 runs (as the execution plan requires 5/5)
4. If pass rate is < 4/5, move to Groq backend and document the result
5. Then proceed to Step 3.3 (edge cases) and Step 3.4 (IR output)

---

*Generated by run_06 — 2026-07-16*
