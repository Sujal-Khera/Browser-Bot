# run_11 — Phase 5: Retry Feedback Loop (Step 5.3)

## Summary

This batch implements BrowserBot's bounded retry feedback loop to automatically recover from transient compilation, import, or runtime dry-run failures during code generation.

1. **Correction Payload (Step 5.3)**: Implemented `CorrectionPayload` to compile structured, minimal error contexts (validation stage, category, failing file, exception text, summary, and a code snippet surrounding the error line) without leaking conversational history or entire files.
2. **Dedicated Retry Coordinator (Step 5.3)**: Built the `PipelineCoordinator` class to manage the retry loop lifecycle (maximum 2 retries). It decouples generation and validation loops from the individual agents.
3. **Prompt Integration (Step 5.3)**: Updated the code generator agent to parse and append correction payload feedback context to the user prompt on retry attempts.
4. **All Tests Passing**: Added 3 new tests in `tests/test_retry_loop.py` validating retry coordinators, compilation of correction payloads, exit on success, and retry bounds. All **55 regression checks** pass cleanly.

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `browserbot/models/correction_payload.py` | **NEW** | Pydantic model representing the structured correction payload. |
| `browserbot/models/__init__.py` | **MODIFIED** | Exposed `CorrectionPayload` in the models public namespace. |
| `browserbot/agents/code_generator/coordinator.py` | **NEW** | `PipelineCoordinator` — orchestrates generation, validation, payload extraction, and retries. |
| `browserbot/agents/code_generator/__init__.py` | **MODIFIED** | Exposed `PipelineCoordinator` in the public package namespace. |
| `browserbot/agents/code_generator/__main__.py` | **MODIFIED** | Integrated `PipelineCoordinator` as the main loop runner in the CLI entry point. |
| `browserbot/agents/code_generator/generator.py` | **MODIFIED** | Updated `generate` and `_generate_body_with_llm` to accept `CorrectionPayload` and pass it down. |
| `browserbot/agents/code_generator/prompt.py` | **MODIFIED** | Instructed the LLM to process correction context payloads. |
| `tests/test_retry_loop.py` | **NEW** | Offline unit tests for pipeline coordinator retries and bounds. |

---

## Retry Architecture

### Why Retries are Outside the Generator
The retry loop is orchestrated by a dedicated `PipelineCoordinator` rather than the `CodeGenerator` itself. This maintains a strict separation of concerns:
- **Generator**: Purely maps a spec (and optional error context) into Python code. It has no capability to execute code or read validation reports.
- **Validator**: Purely runs dynamic checks on written scripts and reports PASS/FAIL status. It has no capability to generate scripts or instruct correction.
- **Coordinator**: Owns the orchestration state machine. It is the only component that knows about retry limits and coordinates execution boundaries. This ensures both generator and validator remain decoupled, making them easier to test and extend.

### Retry Lifecycle
```
[Start] --> Generate Code (Attempt 0)
                 |
           [server.py]
                 |
         Validate Code
                 |
         [Success?] ----(Yes)----> [Exit: overall_success=True]
                 |
               (No)
                 |
        [Attempt >= 2?] --(Yes)--> [Exit: overall_success=False]
                 |
               (No)
                 |
      Extract Correction Payload
                 |
        [Correction Context]
                 |
      Generate Code (Attempt + 1)
```

### Bounded Retry Philosophy
The feedback loop is strictly bounded to a maximum of **2 retries** (3 total attempts). The loop is intended to recover from minor, transient syntax errors or layout changes on the page (like selector mismatches) by providing precise, structured exception text. If a generation fails three times, it represents a permanent logical mismatch or structural issue that requires developer intervention or specification update. Capping retries prevents infinite LLM loop execution, managing latency and api token consumption safely.

---

## Correction Payload

Every correction payload contains the following minimal fields to target LLM correction:
- `validation_stage`: The specific pipeline checkpoint where execution failed (e.g., `"compilation"`, `"import_check"`, `"runtime_dry_run"`).
- `failing_file`: The name of the file that failed (typically `"server.py"`).
- `error_category`: The class of the error encountered (e.g. `"SyntaxError"`, `"ImportError"`, or `"RuntimeError"`).
- `exception`: The exact exception message or traceback details.
- `validation_summary`: A clear summary of the stage failure.
- `relevant_code_snippet`: A narrow window of code (5 lines before and after the failure line) extracted from the generated script to provide local line-by-line context to the LLM.

---

## Validation Results

- **All tests passing**: Running `python -m pytest tests/` executes **55 tests**, all passing.
- **Headed verification run**: Running the pipeline headed successfully completes code generation, dry-run browser execution, and validation in a single coordinated loop:
  ```powershell
  $env:BROWSERBOT_HEADLESS="false"; .venv\Scripts\python.exe -m browserbot.agents.code_generator --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/nobuycart_tracker/
  ```

---

## Future Improvements

*Note: These are documented notes only for later exploration, no changes made.*
- **Self-Healing Selector Repair**: In future phases, if `runtime_dry_run` fails on a locator click, we can read the screenshot or page HTML, identify the updated CSS/XPath selectors, and feed them into the correction payload.

---

## Remaining Work (Phase 6 only)

- **Step 6.1**: Build packaging scripts to build the final executable bundles or container interfaces.
- **Step 6.2**: Dynamic loading of the tool inside Claude Desktop.

---

## Next Batch

**Recommended: Phase 6 (Steps 6.1 + 6.2) - Packaging and Client Integration**

Deliverables:
1. `browserbot/runtime/package.py` to create the deployable tool directories.
2. Installer scripts to configure `config.json` inside Claude Desktop.

---

*Last updated: run_11 — 2026-07-16*
