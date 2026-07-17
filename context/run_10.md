# run_10 — Phase 5: Validator and Dry-Run Harness (Steps 5.1 + 5.2)

## Summary

This batch implements BrowserBot's validation pipeline, introducing a structured verification layer to prove the safety, compilation, importability, and execution correctness of generated FastMCP server tools before they are packaged.

1. **Dry-Run Harness (Step 5.1)**: Developed a lightweight dry-run runner in `harness.py` that dynamically imports generated code and invokes the main workflow method within an isolated asyncio loop using example parameter values, capturing execution metrics (exception, duration, stdout/stderr) and browser screenshots on error.
2. **Validation Pipeline (Step 5.2)**: Structured verification into stages (File Existence, Compilation, Import Check, Runtime Dry-Run, and Output Schema verification), outputting an `overall_success` boolean and saving a `validation_report.json` document.
3. **Pipeline Integration (Step 5.2)**: Integrated validation automatically into the code generator CLI. A generated tool is no longer considered complete unless all verification checks succeed, otherwise exiting with a non-zero code.
4. **All Tests Passing**: Added 6 tests in `tests/test_validator.py` covering compilation failures, import failures, missing output keys, and successful runs. All **52 regression checks** pass successfully.

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `browserbot/models/validation_report.py` | **NEW** | Pydantic data models for structured validation reports. |
| `browserbot/models/__init__.py` | **MODIFIED** | Exposed validation report classes in the models namespace. |
| `browserbot/agents/validator/harness.py` | **NEW** | `DryRunHarness` — imports and runs generated FastMCP tool functions locally. |
| `browserbot/agents/validator/pipeline.py` | **NEW** | `ValidationPipeline` — coordinates stage-by-stage verification checks. |
| `browserbot/agents/validator/__init__.py` | **NEW** | Exposes validation classes. |
| `browserbot/agents/code_generator/validator.py` | **MODIFIED** | Added `first` and `nth` to the approved DSL methods to allow locator indexing. |
| `browserbot/agents/code_generator/prompt.py` | **MODIFIED** | Instructed the LLM to use `.first` to avoid strict-mode tag click errors. |
| `browserbot/agents/code_generator/generator.py` | **MODIFIED** | Appended `.first` to tag-only CSS selectors in dry-run generation logic. |
| `browserbot/agents/code_generator/__main__.py` | **MODIFIED** | Auto-triggered the validation pipeline after writing generated code to disk. |
| `browserbot/templates/mcp_server_template/server.py.j2` | **MODIFIED** | Integrated diagnostic screenshot capture on failure inside the template exception handler. |
| `tests/test_validator.py` | **NEW** | Unit tests for compilation, import checks, dry-run exceptions, and missing outputs. |

---

## Validator Architecture

### Validator Responsibilities
The validation layer acts as an independent quality assurance check. Its sole responsibility is to verify the generated outputs against compile-time and run-time safety invariants:
- Ensure generated files (`server.py`, `mcp_tool.json`) exist.
- Ensure the script complies with Python syntax.
- Ensure the script has no import-time errors.
- Ensure the script executes the target browser workflow successfully and returns a structured output payload containing all expected variables.

### Separation from Generator
The validator is isolated from the generator package. The generator only writes code to disk based on the IR spec; it has no knowledge of how to execute a browser workflow or record run times. Keeping these roles decoupled ensures the generator remains lightweight and the validator can be extended to support headed re-runs, remote runtimes, or self-healing feedback loop agents in the future without changing the code generator architecture.

### Why Validation Occurs Before Packaging
Validating generated artifacts *before* packaging them prevents broken scripts from entering production:
- Saves compute resource (avoids building packaging bundles or Docker images for broken tools).
- Prevents breaking client registrations (crashed FastMCP stdio servers can cause Claude Desktop to hang or drop tools silently).
- Enables early fallback triggers (the orchestrator can catch exit code 1 and immediately prompt for model corrections).

---

## Validation Pipeline

1. **Stage 1: File Existence**: Verifies that both `server.py` (workflow code) and `mcp_tool.json` (metadata descriptor) exist in the target directory.
2. **Stage 2: Python Compilation**: Compiles `server.py` using `py_compile.compile` to check for syntax errors.
3. **Stage 3: Import Check**: Dynamically imports the code using `importlib` spec loaders, verifying that no module-level runtime exceptions occur.
4. **Stage 4: Runtime Dry-Run**: Invokes `run_workflow` using example parameter defaults inside an asyncio loop. Captures execution duration and stdout/stderr.
5. **Stage 5: Expected Output Check**: Parses the JSON response string returned by the tool. Verifies that the status is `"success"` and all outputs required by `WorkflowSpec.outputs` are present.
6. **Stage 6: Screenshot on Failure**: If the dry-run fails, the tool catches the exception, captures a browser screenshot, and writes it to `screenshots/failure_*.png` before exiting. The pipeline logs the screenshot path for diagnostics.

---

## Validation Results

- **All tests passing**: Running `python -m pytest tests/` executes **52 tests**, all passing.
- **Auto-run verification passes**: Running the generation pipeline headed (`BROWSERBOT_HEADLESS=false`) successfully compiles, loads, runs, and passes validation:
  ```powershell
  $env:BROWSERBOT_HEADLESS="false"; .venv\Scripts\python.exe -m browserbot.agents.code_generator --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/nobuycart_tracker/
  ```
  *Result*: Output `overall_success: true` in `validation_report.json`!

---

## Future Improvements

*Note: These are documented notes only for later exploration, no changes made.*
- **Headed/Headless configuration**: Support headed dry-run validation automatically if headless fails, or fall back to headed verification when network assets are blocked.
- **Trace logs capture**: Capture Playwright tracing logs during dry-run validation so developers can view exactly what steps ran.

---

## Remaining Work (Phase 5 only)

- **Step 5.3**: Build the Self-Healing / Repair Agent (Validator feedback to Code Generator).

---

## Next Batch

**Recommended: Phase 5 (Step 5.3) - Repair Loop / Self-Healing**

Deliverables:
1. `browserbot/agents/repair/` agent to read validation failure exception trace and screenshots.
2. Feed exception trace back to the Code Generator prompt as correction input.
3. Automatically retry code generation up to 3 times before returning validation failure.

---

*Last updated: run_10 — 2026-07-16*
