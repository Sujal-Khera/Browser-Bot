# BrowserBot — Developer Orientation Guide
## What You Need to Manually Work Through and Understand

> This file summarises every important thing you need to **personally verify,
> run, or understand** from the six context files (run_01 through run_06).
> Think of it as a checklist + study guide for getting fully up to speed.

---

## How to Use This Guide

Work through each section **in order**. Each section maps to one run file.
The columns mean:

- **What to do** — the hands-on action you need to take
- **Why it matters** — what breaks later if you skip it
- **Status** — whether it was confirmed automatically or needs your manual check

---

## 1. Phase 1 — Environment + Scaffolding + Ground Truth Script (run_01)

### 1.1 Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python scripts/verify_env.py --no-ollama` and confirm you see `6/6 checks passed` | This is your baseline. If any dependency is missing, every later phase will fail silently |
| B | Run `python -m browserbot.recorder --demo` and confirm it prints `Example Domain` | Verifies Playwright Chromium works. If it fails, fix Playwright before touching anything else |
| C | Open `tests/fixtures/ground_truth_script.py` and read it top to bottom | This is the *hand-written* baseline the entire project measures itself against. You must understand what it does |

### 1.2 Things You Must Understand (Not Just Run)

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | The **demo site is `nobuycart.com/tracking/`** — a fake order tracking simulator | `tests/fixtures/nobuycart_tracking_script.py`, `docs/schemas/action_log_example.json` | Every LLM prompt, every test fixture, every schema example uses this site. If you don't understand what this site does (enter a fake order code → see a fake shipping timeline), nothing downstream will make sense |
| E | The **ground truth script** is your reliability baseline | `tests/fixtures/ground_truth_script.py` | The execution plan says: run it 10 times and record pass rate. This number is your "before automation" benchmark. Do this manually. |
| F | Why `D-01` (URL not hardcoded) was a deliberate decision | `run_01.md` Decision D-01 | If you add a real URL, you need to update the selectors. If you don't, the script fails loudly (which is correct behaviour). |

### 1.3 Manual Tasks You Still Need to Do

- [ ] Run `tests/fixtures/nobuycart_tracking_script.py` manually and watch the browser automation to understand what the workflow actually looks like
- [ ] Fill in the 10-run reliability table in `run_01.md` (it currently says `TBD`)

---

## 2. Phase 1.4 + Phase 2.1 — FastMCP Hello Tool + Action Log Schema (run_02)

### 2.1 Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Open `browserbot/runtime/hello_tool.py` and read the `@mcp.tool` decorator pattern | Every generated MCP tool in Phase 4 will use this exact same pattern. This is the template you need to understand |
| B | Run the hello tool: `python -m browserbot.runtime.hello_tool` — then read the `claude_desktop_config.example.json` | Understand how Claude Desktop connects to a local FastMCP server. This is how the end product will be installed |
| C | Open `docs/schemas/action_log_schema.json` and read it completely | This is the **frozen contract** for the entire project. Every later agent reads from or writes to this schema |
| D | Open `docs/schemas/action_log_example.json` | This is the canonical example of a recorded session. It represents the NoBuyCart tracking workflow in structured form |

### 2.2 Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| E | **What an ActionLog is** | `browserbot/models/action_log.py` | Every phase (recorder, scrubber, extractor, generator, validator) talks to each other through ActionLog objects. If you don't understand its structure, you can't understand any phase |
| F | **Why `additionalProperties: false`** on every schema object | `run_02.md` AN-03 | If the LLM or recorder invents a new field, validation fails loudly. This is a deliberate design choice, not an accident |
| G | **Why `step_index` is checked for ordering** | `browserbot/models/action_log.py` | Steps must arrive in order (0, 1, 2...). This is enforced at parse time, not at runtime. Understanding this prevents a whole class of bugs |
| H | **Why `extracted_text` is recorded at capture time** | `run_02.md` AN-06 | The Validator (Phase 5) compares replay output against the recorded `extracted_text`. If you assume it's empty, Phase 5 won't make sense |

### 2.3 Manual Tasks

- [ ] Optionally: configure Claude Desktop with the hello tool and confirm it responds (from `run_02.md` "To verify with Claude Desktop" section)
- [ ] Read `browserbot/models/action_log.py` in full — at least the docstring and each Step class definition

---

## 3. Phase 2.2 + 2.3 — Browser Recorder (run_03)

### 3.1 Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python scripts/validate_step_2_2.py` and confirm `6/6 checks passed` | This is the integration test for the entire Recorder pipeline. If any check fails, the Phase 3 extractor will receive bad input |
| B | Try the recording CLI yourself: `python -m browserbot.recorder start https://nobuycart.com/tracking/` | Record a short workflow (enter a fake order code, click the button). Watch the JSON file appear in `workflows/sessions/`. Open it. Does it look like `action_log_example.json`? |

### 3.2 Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| C | **How the codegen converter works** | `run_03.md` "Converter Design" section, `browserbot/recorder/convert_codegen.py` | This is how raw Playwright codegen Python output turns into structured JSON. Understanding the regex-to-step mapping helps you debug bad recordings |
| D | **Why regex was chosen over AST parsing** | `run_03.md` "Why Regex Rather Than AST Parsing" | Design rationale. If you ever need to add a new action type to the converter, you need to understand this trade-off |
| E | **The full pipeline order**: `codegen → raw_script.py → convert → scrub → to_file()` | `run_03.md` Summary | This sequence must be respected. You can't swap any step out without breaking the security guarantees (scrub comes before disk write — always) |

### 3.3 Manual Tasks

- [ ] Actually record a session using the CLI and inspect the output JSON
- [ ] Check that `workflows/sessions/` is in your `.gitignore` (it should be — you don't want to commit real session data)

---

## 4. Phase 2.4 — PII Scrubber (run_04)

### 4.1 Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_scrubber.py -v` and confirm `13/13 passed` | 13 tests cover every scrubbing scenario. All must pass before you trust that sensitive data is protected |
| B | Read `browserbot/recorder/scrubber.py` top to bottom, including the module docstring | The docstring explains the full security model: why values are replaced (not deleted), how placeholders are assigned, what the `value_map` is and why it's never written to disk |

### 4.2 Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| C | **What triggers scrubbing** | `scrubber.py` `DEFAULT_SENSITIVE_KEYWORDS` | The scrubber uses keyword matching on the selector value and field label. Know what keywords are in the list (password, token, secret, etc.) so you can predict what gets scrubbed |
| D | **What `__SECRET_1__` means** | `run_04.md` "Placeholder Strategy" | These placeholders appear in the session JSON. Phase 3 (Pattern Extractor) will see them. The extractor is told to treat them as `is_sensitive=True` parameters. |
| E | **Why the scrubber is a pure function** | `run_05.md` Issue #1 | The original scrubber mutated the ActionLog in place. This was fixed. `scrub(action_log)` never changes `action_log` — always use `result.action_log` for the scrubbed version |
| F | **What `BROWSERBOT_SENSITIVE_SELECTORS` env var does** | `scrubber.py` docstring | You can add custom selectors to always scrub, without changing code. Useful if your target site has non-standard field names |

### 4.3 Manual Tasks

- [ ] Record a session that includes a field you'd want scrubbed (e.g. a login form). Open the resulting session JSON and verify the password value is `__SECRET_1__`, not the real password
- [ ] Note: the NoBuyCart site has NO sensitive fields — so the scrubber will not redact anything for that workflow. This is correct behaviour.

---

## 5. Architecture Freeze (run_05)

### 5.1 Things You Must Understand

This run made no new features — it fixed bugs. But these bugs were **critical**:

| # | Bug fixed | What it means for you |
|---|-----------|----------------------|
| A | `object.__setattr__` on Pydantic v2 model | The scrubber was silently bypassing Pydantic's type system. Now it uses `model_copy()`. If you ever write Pydantic code, never use `object.__setattr__` to mutate a model |
| B | Tests were asserting on the original `action_log` after `scrub()` | They were testing nothing. This is a common testing mistake: test the thing you changed, not the original |
| C | No post-scrub schema validation | The pipeline could write a schema-invalid file to disk. Now `ActionLogValidator.assert_valid()` runs between `scrub()` and `to_file()` |

### 5.2 Frozen Interfaces (Read These — They Are Phase 3's Input Contract)

These APIs are **stable and will not change**. Phase 3 depends on them:

```python
# Load a session from disk
log = ActionLog.from_file(path)

# Scrub it (pure function — original unchanged)
result = scrub(log)
scrubbed_log = result.action_log   # Use THIS, not log

# Validate the scrubbed log
validator = ActionLogValidator()
validator.assert_valid(scrubbed_log.model_dump(mode="json"), label="check")
```

- [ ] Read the full "Interfaces Frozen" section in `run_05.md` — this is the contract Phase 3 (which you are now using) was built against

---

## 6. Phase 3 — Pattern Extractor + Confirmation (run_06) ← Current State

### 6.1 Things You Must Verify Manually

| # | What to do | Command | Expected |
|---|-----------|---------|----------|
| A | Run all tests | `python -m pytest tests/ -v` | `30 passed` |
| B | Run the dry-run CLI | `python -m browserbot.agents.pattern_extractor --dry-run --yes --json tests/fixtures/extractor_test_session.json` | JSON output with `fake_order_code` parameter |
| C | Run the validation script | `python scripts/validate_step_2_2.py` | `6/6 checks passed` |

### 6.2 Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **The prompt is intentionally narrow** | `browserbot/agents/pattern_extractor/prompt.py` module docstring | The LLM is told ONLY to classify steps as parameters or fixed. It is forbidden from reasoning about Playwright or generating code. This narrowness is what makes smaller models reliable |
| E | **Why temperature = 0.0** | `extractor.py` class docstring | Determinism over creativity. Pattern classification is not a creative task |
| F | **The retry loop with correction injection** | `extractor.py` `_inject_correction()` | When the model produces bad JSON, the error is shown back to the model before retrying. This is more effective than a cold restart |
| G | **The three-level JSON extraction** | `extractor.py` `_extract_json_from_text()` | Local models sometimes wrap JSON in markdown fences or add trailing text. The extractor handles all three cases before giving up |
| H | **Dry-run mode produces conservative results** | `extractor.py` `_build_dry_run_output()` | In dry-run, ALL fill steps become parameters. The real LLM is smarter — it only flags fill steps whose values change per run. You confirm/correct this in Step 3.2 |
| I | **`result.action_log` not `action_log`** | `run_05.md`, `test_scrubber.py` | After calling `scrub()`, always use `result.action_log`. The original is unchanged. This same pattern applies in `extractor.py`: `result` carries the output, not the input |
| J | **The extractor output schema** | `docs/schemas/extractor_output_schema.json` | The LLM response is validated against this schema before any downstream step sees it. Invalid LLM output = retry, not crash |

### 6.3 Manual Tasks You Need to Do Next

#### The Critical Manual Task — Run Against Real Ollama

The dry-run mode is confirmed working. But you **have not yet run the real LLM**.
The execution plan requires 5/5 consistency runs. Do this manually:

```powershell
# Step 1: Make sure Ollama is running
ollama serve

# Step 2: Pull the model if you haven't
ollama pull llama3.1:8b

# Step 3: Record a real session (or use the existing fixture)
python -m browserbot.recorder start https://nobuycart.com/tracking/

# Step 4: Run the extractor against the real session (replace with your actual file)
python -m browserbot.agents.pattern_extractor `
  workflows/sessions/session_TIMESTAMP.json

# Step 5: Repeat 5 times and record results:
```

| Run | Did it identify `order_id` (or equivalent)? | Response time | Notes |
|-----|---------------------------------------------|---------------|-------|
| 1   | TBD | — | — |
| 2   | TBD | — | — |
| 3   | TBD | — | — |
| 4   | TBD | — | — |
| 5   | TBD | — | — |
| **Pass rate** | — / 5 | — | Need ≥ 4/5 to stay on Ollama |

> **If pass rate < 4/5**: Switch to Groq. Set `BROWSERBOT_LLM_BACKEND=groq` and
> `GROQ_API_KEY=your_key_here` in `.env` and re-run.

#### The Confirmation UX — Try It Interactively

The `--yes` flag auto-accepts everything. But the real workflow requires human input. Try it without `--yes`:

```powershell
python -m browserbot.agents.pattern_extractor `
  --dry-run `
  tests/fixtures/extractor_test_session.json
```

- Press `Enter` to accept
- Press `r` to rename (try renaming `fake_order_code` to `order_id`)
- Press `n` to reject a parameter
- After review, add a missed parameter manually

---

## 7. The Big Picture — What You Now Have

```
[Browser] --> [Playwright Codegen] --> [raw_script.py]
                                            |
                                    [convert_codegen_file()]
                                            |
                                    [ActionLog (in memory)]
                                            |
                                       [scrub()]
                                            |
                              [ScrubResult.action_log]
                                            |
                              [ActionLogValidator.assert_valid()]
                                            |
                              [session_TIMESTAMP.json] (on disk)
                                            |
                              [PatternExtractor.extract()]
                                            |
                              [ExtractorOutput (in memory)]
                                            |
                              [confirm_parameters()]  <-- YOU ARE HERE
                                            |
                              [ConfirmedOutput]
                                            |
                                   PHASE 4 (next)
                              [Code Generator -- NOT YET BUILT]
```

---

## 8. What Is NOT Built Yet

These are the remaining phases. Do NOT attempt to use or test them — they are empty stubs:

| Phase | What it does | Status |
|-------|-------------|--------|
| Phase 3.3 | Edge case handling (zero params, multiple params) | **NOT STARTED** |
| Phase 3.4 | Intermediate Representation (`workflow_spec.json`) | **NOT STARTED** |
| Phase 4 | Code Generator (LLM → Playwright script) | **NOT STARTED** |
| Phase 5 | Validator (auto-test generated code) | **NOT STARTED** |
| Phase 6 | FastMCP Tool Generator | **NOT STARTED** |
| Phase 7 | Packaging + Claude Desktop integration | **NOT STARTED** |
| Phase 8 | Self-healing selectors | **NOT STARTED** |

---

## 9. Quick Command Reference

```powershell
# Run all tests
python -m pytest tests/ -v

# Run scrubber tests only
python -m pytest tests/test_scrubber.py -v

# Run extractor tests only
python -m pytest tests/test_pattern_extractor.py -v

# Validate the recorder pipeline
python scripts/validate_step_2_2.py

# Verify environment
python scripts/verify_env.py --no-ollama

# Record a new session
python -m browserbot.recorder start https://nobuycart.com/tracking/

# Run pattern extractor (dry-run, auto-confirm, JSON output)
python -m browserbot.agents.pattern_extractor --dry-run --yes --json tests/fixtures/extractor_test_session.json

# Run pattern extractor (real Ollama, interactive confirmation)
python -m browserbot.agents.pattern_extractor workflows/sessions/session_YOUR_TIMESTAMP.json

# Run pattern extractor with Groq fallback
python -m browserbot.agents.pattern_extractor --backend groq workflows/sessions/session_YOUR_TIMESTAMP.json
```

---

## 10. Known Issues You Should Be Aware Of

| Issue | Impact | What to do |
|-------|--------|-----------|
| Dry-run names parameters from the CSS selector, not semantically (e.g. `fake_order_code` instead of `order_id`) | Low — you rename it in Step 3.2 confirmation | Use the rename option in the CLI, or use the real Ollama model |
| PowerShell shows exit code 1 when stderr has content, even if the program succeeded | Confusing terminal output | Ignore the red text if the program says "Done" at the end. Or pipe with `2>$null` |
| `settings.llm_max_retries` defaults to 3 retries | Ollama calls can be slow | Reduce with `BROWSERBOT_LLM_MAX_RETRIES=1` env var for faster iteration |
| `WaitStep` with `wait_for="selector"` requires a selector but schema doesn't enforce it | Rare recorder edge case | If replay fails on a wait step, check the session JSON manually |
| `ExtractTextStep.extracted_text` is always `""` after conversion | Phase 5 (Validator) depends on this | Normal for now — `extracted_text` gets populated at replay time in Phase 5 |

---

*Last updated: run_06 — 2026-07-16*

---

## 7. Phase 3B — Intermediate Representation (run_07)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_pattern_extractor.py -v` and confirm all `20 passed` | Validates that the zero, single, and multi-parameter edge cases parse, extract, and compile to IR successfully. |
| B | Inspect the generated `workflows/sessions/workflow_spec_nobuycart.json` file | Verifies that a real recorded session converts into a valid, schema-compliant Intermediate Representation (IR). |
| C | Open `docs/schemas/workflow_spec_schema.json` and read the schema fields | You must understand the schema definition of the spec, as this is the exact contract consumed by Phase 4. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **What the IR is** | `browserbot/models/workflow_spec.py` | A versioned, serializable logical model of the workflow steps and parameters, completely isolated from Playwright execution details. |
| E | **Why it is independent from Playwright** | `run_07.md` | It represents the *logic* of the workflow (inputs, actions, outputs), allowing downstream generators to change without impacting extraction logic. |
| F | **Optional and Repeated parameters** | `tests/fixtures/session_multi_params.json` | Shows how repeated secret values map to the same placeholder and how parameters can be designated as optional (`is_optional`). |
| G | **How output values are tracked** | `browserbot/agents/pattern_extractor/generator.py` | Extraction actions (`extract_text`, `extract_attribute`) are automatically identified and mapped into the `outputs` list in the IR. |

### Manual Tasks

- [ ] Run the pattern extractor on your own recorded session without `--yes` and try marking a parameter optional using the `o` choice key in the confirmation CLI.
- [ ] Verify that the generated spec file contains your confirmed parameter names and maps them correctly under the `parameter_name` key in the steps.

---

*Last updated: run_07 — 2026-07-16*

---

## 8. Phase 4A — Deterministic Code Generation (run_08)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_code_generator.py -v` and confirm all `11 passed` | Validates that the AST DSL validator correctly blocks/permits statements, and that the Jinja2 template renders and compiles. |
| B | Run `python -m py_compile generated_tools/check_order_status/server.py` | Confirms the generated server file is syntactically valid Python. |
| C | Open `browserbot/templates/mcp_server_template/server.py.j2` and read the template structure | Understand the lifecycle managers and logging wrapper definitions generated around the workflow body. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **The Template vs LLM split** | `run_08.md` | The template handles all imports, FastMCP wrappers, error handling, and browser setup. The LLM only maps the page interaction steps. |
| E | **Approved DSL and Validator** | `browserbot/agents/code_generator/validator.py` | Security gate. The visitor checks every AST node in the LLM code block and raises `DSLValidationError` if an import, subprocess, or unauthorized variable load is found. |
| F | **Headless configuration** | `server.py.j2` | The template reads the `BROWSERBOT_HEADLESS` environment variable, enabling seamless switching between background and visible test runs. |

### Manual Tasks

- [ ] Run the generator CLI with `--dry-run` to output a server file: `python -m browserbot.agents.code_generator --dry-run --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/check_order_status/server.py`.
- [ ] Open the output file and confirm the `run_workflow` function contains your parameter bindings (e.g. `.fill(fake_order_code)`) in the steps sequence.

### Architecture Notes

- Chaining locator methods (e.g. `page.get_by_role(...).fill(...)`) is resolved recursively in AST parsing. Only approved methods are allowed in calls.
- Unassigned local variables (except parameters and page) are prohibited. New local variables are registered when defined via assignments in the AST.

---

*Last updated: run_08 — 2026-07-16*

---

## 9. Phase 4B — Complete Generation Pipeline (run_09)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_manifest.py -v` and confirm all `2 passed` | Validates that the manifest generator works correctly and that invalid manifests are caught by schema validation. |
| B | Verify that `generated_tools/nobuycart_tracker/mcp_tool.json` exists | Confirms the complete pipeline successfully created the stdio server and its registry manifest side-by-side. |
| C | Open `docs/schemas/mcp_tool_schema.json` and read the manifest JSON schema | Enforces strict validation of parameters schema, required properties, and metadata format. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Tool Manifest Role** | `run_09.md` | The manifest contains tool descriptions, names, and parameters required by LLM clients (like Claude) to register and select tools. |
| E | **Relationship: Spec vs Manifest** | `run_09.md` | The spec IR is a developer-facing workflow definition. The manifest is a client-facing API declaration. |
| F | **Deterministic Generation** | `browserbot/agents/code_generator/manifest.py` | Writing the manifest must be mechanical. Hallucinating schema formats or fields is prohibited. |

### Manual Tasks

- [ ] Inspect the generated `generated_tools/nobuycart_tracker/mcp_tool.json` file. Assert that its properties match `workflow_spec_nobuycart.json` parameters.
- [ ] Run the generated server `python generated_tools/nobuycart_tracker/server.py` and verify it starts and registers the tool name `execute_nobuycart_com` correctly.

---

*Last updated: run_09 — 2026-07-16*

---

## 10. Phase 5A — Validator & Dry-Run Harness (run_10)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_validator.py -v` and confirm all `6 passed` | Validates that the validator pipeline successfully handles compilation failures, imports checks, output checks, and dry-run errors. |
| B | Verify that `generated_tools/nobuycart_tracker/validation_report.json` exists | Confirms the code generator CLI automatically executed validation and saved the structured report on disk. |
| C | Open `validation_report.json` and read the JSON schema stage outputs | Verifies the metrics of the runtime dry-run and compile results. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Harness dynamic importing** | `browserbot/agents/validator/harness.py` | Imports the server module dynamically at runtime using spec loaders, enabling off-line checks without running subprocesses. |
| E | **Validation layers** | `browserbot/agents/validator/pipeline.py` | Runs stages sequentially: Existence $\rightarrow$ Compilation $\rightarrow$ Import $\rightarrow$ Dry-Run $\rightarrow$ Outputs. Stops on first fail. |
| F | **Diagnostics (Screenshots)** | `server.py.j2` | The template captures failure screenshots when BROWSERBOT_FAILURE_SCREENSHOT_PATH is defined, allowing developers to see browser state at crash time. |

### Manual Tasks

- [ ] Run the generator with `BROWSERBOT_HEADLESS=false` to trigger a headed dry-run validation. Verify the browser opens, inputs variables, and closes cleanly.
- [ ] View a failure screenshot under `screenshots/` after a failed dry-run (e.g. timeout) to inspect the browser state.

---

*Last updated: run_10 — 2026-07-16*

---

## 11. Phase 5B — Retry Feedback Loop (run_11)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_retry_loop.py -v` and confirm all `3 passed` | Validates that the coordinator terminates within 2 retries, triggers correction, and exits immediately on success. |
| B | Check that `browserbot/models/correction_payload.py` has no lints | Ensures the data schema model for correction payload is correct and clean. |
| C | Open a generated `server.py` and inspect the workflow body comments | Verifies the code generator LLM correctly resolved the feedback loop and output valid statement sequences. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Decoupled Orchestration** | `browserbot/agents/code_generator/coordinator.py` | PipelineCoordinator acts as the outer state machine, keeping retry logic isolated from LLM and validation layers. |
| E | **Correction Prompting** | `browserbot/agents/code_generator/prompt.py` | User prompt appends the validation stage, exception traceback, and failing code snippet under the PREVIOUS GENERATION ERROR section. |
| F | **Snippets extraction** | `browserbot/agents/code_generator/coordinator.py` | Extracts a narrow 10-line slice around the error line number, keeping LLM context window small. |

### Manual Tasks

- [ ] Modify a `workflow_spec.json` step manually to contain an invalid CSS selector (e.g. `div:invalid`), run the generator CLI, and observe in the log output how compilation fails, compiles the payload context, and retries.

---

*Last updated: run_11 — 2026-07-16*

---

## 12. Phase 6A — Packaging & Installation (run_12)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_packager.py -v` and confirm all `6 passed` | Validates that the package generator creates manifests, installs dependencies, templates PowerShell scripts, and verifies install status. |
| B | Run `python -m browserbot.agents.packager --input generated_tools/nobuycart_tracker --output packages/execute_nobuycart_com` | Compiles the installable tool package and verifies its structure. |
| C | Verify that `packages/execute_nobuycart_com/browserbot_package.json` exists | Confirms the compiler successfully created the package metadata manifest descriptor. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Package Structure** | `browserbot/agents/packager/packager.py` | Encapsulates code, tool manifests, verification reports, requirements, and PowerShell config scripts. |
| E | **Installation Verification** | `browserbot/agents/packager/packager.py` | Checks schema constraints, file existence, and simulates mock integration into Claude Desktop config files. |
| F | **Isolated Registry** | `docs/schemas/package_schema.json` | Keeps installation state and registration declarative, avoiding direct side-effects on developer machines. |

### Manual Tasks

- [ ] Inspect the generated package under `packages/execute_nobuycart_com/`. Ensure `install.ps1` contains the absolute path to `server.py`.
- [ ] Read `browserbot_package.json` and verify the `claude_config_snippet` has the correct `command` and `env` properties.

---

*Last updated: run_12 — 2026-07-16*

---

## 13. Phase 6B — Registry & Result Formatting (run_13)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_registry.py -v` and confirm all `10 passed` | Validates the registry correctly creates, merges, backs up, and removes Claude Desktop config entries. |
| B | Run `python -m browserbot.runtime register --package packages\execute_nobuycart_com --dry-run` | Confirms the registry resolves the correct `%APPDATA%\Claude\claude_desktop_config.json` path and prints the right snippet. |
| C | Run `python -m pytest tests/test_result_formatting.py -v` and confirm all `18 passed` | Validates that `format_success` never returns raw JSON and `format_error` never exposes tracebacks. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Registry is additive, never destructive** | `browserbot/runtime/registry.py` | The registry merges into `mcpServers` without touching other entries. If Claude Desktop already has tools registered, they are preserved. |
| E | **Error sentinel must stay in sync** | `result_formatter.py` `_ERROR_SENTINEL`, `harness.py` line checking | `format_error` always starts with `"I wasn't able to complete the workflow"`. The `DryRunHarness` uses this exact prefix to detect error returns. If you change one, change both. |
| F | **Tools return prose, not JSON** | `server.py.j2`, `result_formatter.py` | Generated tools return human-readable strings Claude can relay verbatim. The internal dict is never serialized to `json.dumps()` in the tool return anymore. |
| G | **Backup before write** | `registry.py` `_backup_config()` | The registry always creates a timestamped `.bak.json` before modifying the Claude Desktop config. If something goes wrong, the original is preserved. |

### Manual Tasks

- [ ] **Complete the live registration**: Run `python -m browserbot.runtime register --package packages\execute_nobuycart_com`, restart Claude Desktop, then ask: *"Check my order status for order code NBC-2026-E3ZXJC"*
- [ ] **Test 3 paraphrased questions** to confirm Claude reliably selects the tool
- [ ] **Test the error path**: Edit the generated `server.py` to use an unreachable URL, run the tool, confirm Claude responds with a clean error message (not a traceback)

### Quick Command Reference

```powershell
# Register tool with Claude Desktop
python -m browserbot.runtime register --package packages\execute_nobuycart_com

# Dry-run (print config snippet without writing)
python -m browserbot.runtime register --package packages\execute_nobuycart_com --dry-run

# List all registered tools
python -m browserbot.runtime list

# Unregister a tool
python -m browserbot.runtime unregister --tool execute_nobuycart_com

# Run all tests
python -m pytest tests/ -v   # 89 passed
```

---

*Last updated: run_13 — 2026-07-17*

---

## 14. Phase 7A — End-to-End Validation (run_14)

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Run `python -m pytest tests/test_integration.py -v` and confirm all `3 passed` | Validates that the entire sequential compilation and registration pipeline completes without errors under dry-run conditions. |
| B | Run the full suite: `python -m pytest tests/ -v` | Confirms that all 92 tests are green, proving no regression was introduced. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| C | **Orchestration Pipeline Role** | `browserbot/orchestrator/pipeline.py` | Orchestration acts as the central coordinator, chaining all existing subsystem modules sequentially. It is programmatic, deterministic, and will act as the backend API wrapper for the Phase 7B UI. |
| D | **Hermetic Testing** | `tests/test_integration.py` | The tests mock the Playwright browser dry-run harness to prevent external internet/website dependency, ensuring 100% offline reliability in all development environments. |

### Manual Verification Steps

1. Start with a raw recorded session:
   ```powershell
   python -m browserbot.recorder start https://nobuycart.com/tracking/
   ```
2. Manually run the pipeline orchestrator end-to-end to generate, validate, package, and register the tool:
   - Programmatically run the pipeline from Python:
     ```python
     from pathlib import Path
     from browserbot.orchestrator import OrchestrationPipeline
     
     pipeline = OrchestrationPipeline(dry_run=True)
     pipeline.run(
         raw_action_log_path="workflows/sessions/session_TIMESTAMP.json",
         output_dir="generated_tools/nobuycart_tracker",
         package_dir="packages/execute_nobuycart_com",
         register=True
     )
     ```
3. Restart Claude Desktop and verify the tool is registered and callable.

### Known Limitations & Debugging Tips

* **Windows Store Path redirection**: If Claude Desktop still doesn't see your tool, verify the registry is outputting `Config: ...\Claude_...\LocalCache\Roaming\...`. The registry supports this, but make sure your Windows Store installation folder matches the naming style.
* **Orchestration exception traces**: If the pipeline fails, inspect the `PipelineOrchestrationError` message. It specifies exactly which stage (Stage 1 to 7) triggered the failure, making troubleshooting straightforward.
* **Duplicate Parameter Names Bug Fixed**: If your recorded session targets identical fields or generates duplicate parameter name recommendations, the generator now automatically de-duplicates them (e.g. `textbox_fake_order_code` and `textbox_fake_order_code_2`) to prevent Python function definition `SyntaxErrors`.

*Last updated: run_14 — 2026-07-17*

## 15. Phase 7B — Production Readiness (run_15)

This run hardens BrowserBot through regression validation, determinism protection, structured diagnostics, and exception handling improvements.

### Things You Must Verify Manually

* **Verification of `pipeline_diagnostics.json`**: After running the orchestrator pipeline (e.g., via `python run_sample.py`), navigate to the generated output directory (`generated_tools/nobuycart_tracker/`) and confirm `pipeline_diagnostics.json` exists. Open it and verify all 7 stages show `success: true` and no errors.
* **Diagnostics under Failure States**: Deliberately insert an invalid file path or cause validation to fail, run the pipeline, and verify the diagnostics file is written with the active stage marked as failed, alongside the exact exception description.

### Things You Must Understand

* **Diagnostics Observability**: The `pipeline_diagnostics.json` report acts as a single point of telemetry for the entire pipeline, logging metadata, timing, and error traces. This enables user interface layers and wrapper processes to inspect compilation status without reading logs directly.
* **Strict Determinism**: End-to-end execution must remain 100% deterministic. Running the compilation process repeatedly over the same session log produces identical AST outputs, requirements declarations, and package metadata (excluding execution timestamps).

### Manual Tasks

1. To run full regression and integration tests to verify production readiness:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -v
   ```
2. Verify happy-path compilation, packaging, and automatic Claude Desktop integration:
   ```powershell
   .venv\Scripts\python.exe run_sample.py
   ```

### Architecture Notes

* **Telemetry Output**: Telemetry details are recorded inside the `OrchestrationPipeline.run()` execution flow. The stages dictionary tracks step transitions non-destructively, persisting to disk under `output_dir / "pipeline_diagnostics.json"`.

### Command Reference

* **Test execution**: `.venv\Scripts\python.exe -m pytest tests/ -v`
* **Workflow run**: `.venv\Scripts\python.exe run_sample.py`

---

*Last updated: run_15 — 2026-07-17*

## 16. Phase 8A — Selector Resilience (run_16)

This run implements Phase 8A selector resilience by introducing dynamic prioritized fallback locator resolution.

### Things You Must Verify Manually

* **Verification of Resilience Logging**: Run a workflow (e.g. `python run_sample.py`) and inspect the terminal output or output logs. Confirm you see:
  `Resolving locator with prioritized fallbacks` followed by `Locator resolved successfully`.
* **Playwright Native Failure Propagation**: Deliberately run the tool on an empty/wrong page or selector that doesn't exist under any candidate variant, and confirm the tool exits with standard Playwright timeout exceptions rather than a silent failure.

### Things You Must Understand

* **Prioritised Fallback Ordering**: The dynamic resolver compiles locator candidates deterministically: ARIA Role -> Label -> Placeholder -> Test ID -> Text -> Raw Selector. It searches for these in order and matches on the first one present on the page.
* **DSL Safety Preservation**: The resolver lives in `browserbot.runtime.resilience`. Whitelisting `resolve_locator` in the validator allows compiler statements like `await (await resolve_locator(page, selector)).click()` to validate and compile successfully, while fully preserving the security restrictions on arbitrary Python execution.

### Manual Tasks

1. Run the resilience unit tests:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_resilience.py -v
   ```
2. Run the complete regression test suite:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -v
   ```

### Architecture Notes

* **resilience.py**: The resolver helper `resolve_locator` polls each candidate locator at `100ms` intervals. If no match is found before the timeout, it yields the first candidate to defer matching errors to Playwright.

### Command Reference

* **Resilience tests**: `.venv\Scripts\python.exe -m pytest tests/test_resilience.py -v`
* **All tests**: `.venv\Scripts\python.exe -m pytest tests/ -v`

---

*Last updated: run_16 — 2026-07-17*

## 17. Phase 8B — Adaptive Selector Recovery (run_17)

This run completes Phase 8 resilience by implementing runtime timing resilience and a programmatic self-healing loop.

### Things You Must Verify Manually

* **Verification of Timing Resilience**: Run `python run_sample.py` and inspect logging traces. Confirm that actions now log:
  `Page network state settled (networkidle)` followed by `Resilient click succeeded` or `Resilient fill succeeded`.
* **Verification of Self-Healing CLI**: Run:
  ```powershell
  .venv\Scripts\python.exe -m browserbot.runtime self-heal --package packages/execute_nobuycart_com --force
  ```
  Verify that the self-healing workflow recursively locates the source session ID action log, re-compiles the tool, runs AST validation, performs verification tests, and re-registers the server.

### Things You Must Understand

* **Action Retry with Backoff**: All clicks and fills are wrapped in `resilient_click` and `resilient_fill` helpers which wait for `networkidle` state and run dynamic element resolution inside an exponential backoff loop (`0.1s`, `0.5s`, `1.0s`, `2.0s`).
* **Self-Healing Flag Trigger**: When a generated tool encounters an execution exception at runtime, the catch block writes a `needs_healing.flag` file to the package directory. A wrapper execution script or `browserbot.runtime self-heal` uses this flag to discover damaged tools and heal them.

### Manual Tasks

1. Run the self-healing and timing resilience unit tests:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_self_healing.py -v
   ```
2. Run the complete regression test suite:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -v
   ```

### Architecture Notes

* **self_healing.py**: Contains the `self_heal_package` routine which maps a failing package directory back to its raw session recording log using `metadata.source_session_id`, executes the compiler pipeline, and clears the failure flag on success.

### Command Reference

* **Self-healing tests**: `.venv\Scripts\python.exe -m pytest tests/test_self_healing.py -v`
* **Trigger package healing**: `.venv\Scripts\python.exe -m browserbot.runtime self-heal --package packages/execute_nobuycart_com --force`
* **All tests**: `.venv\Scripts\python.exe -m pytest tests/ -v`

### Common Failure Scenarios

* **Missing Source Session Log**: If a package's original source session recording log JSON file is deleted from the `workflows/sessions/` directory, self-healing will raise a `FileNotFoundError`. The original recordings must be preserved for self-healing capability.

---

*Last updated: run_17 — 2026-07-17*

## 18. Phase 9A — Performance & Observability (run_18)

This run implements performance timing instrumentation inside the pipeline orchestrator, along with PII credential scanning and automated latency/reliability benchmark runners.

### Things You Must Verify Manually

* **Verification of PII Scanning CLI**: Run:
  ```powershell
  .venv\Scripts\python.exe scripts/pii_audit.py --package packages/execute_nobuycart_com
  ```
  Confirm it prints: `PII Audit passed successfully! No credentials or secrets found.` and exits with code `0`.
* **Verification of NFR Benchmark CLI**: Run:
  ```powershell
  .venv\Scripts\python.exe scripts/run_benchmark.py --package packages/execute_nobuycart_com --iterations 3
  ```
  Verify it runs successfully, prints execution timing statistics (mean, minimum, maximum latencies, standard deviations), and writes compliance files `benchmark_report.json` and `benchmark_report.md` inside the package directory.

### Things You Must Understand

* **Pipeline Timing Instrumentation**: Stage timing measurements are dynamically calculated in the orchestrator pipeline run using `time.perf_counter()` and recorded inside the output directory's `pipeline_diagnostics.json` file.
* **PII Redaction Auditor regexes**: The credential scan whitelists standard placeholders (e.g. `__SECRET_1__`) but flags raw hex keys, JWT signatures, literal test passwords, and unredacted values.

### Manual Tasks

1. Run the performance and observability unit tests:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_observability.py -v
   ```
2. Run the complete regression test suite:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -v
   ```

### Architecture Notes

* **pii_audit.py**: Contains the `audit_artifacts` scanner function verifying credential scrubbing completeness in generated scripts.
* **benchmark.py**: Houses the `run_benchmark` async routine which imports workflow entry points dynamically, measures tool latencies, gathers pipeline compile times, checks reliability, and evaluates NFR goals.

### Command Reference

* **Observability tests**: `.venv\Scripts\python.exe -m pytest tests/test_observability.py -v`
* **PII Audit execution**: `.venv\Scripts\python.exe scripts/pii_audit.py --package packages/execute_nobuycart_com`
* **Benchmark runner**: `.venv\Scripts\python.exe scripts/run_benchmark.py --package packages/execute_nobuycart_com --iterations 3`
* **All tests**: `.venv\Scripts\python.exe -m pytest tests/ -v`

### Performance Diagnostics

* **Benchmark Reports**: Benchmarking generates structured outputs in the package folder:
  - `benchmark_report.json`: raw metrics (latencies list, compilation timelines).
  - `benchmark_report.md`: formatted markdown table summarizing compliance against targets.

---

*Last updated: run_18 — 2026-07-17*

## 19. Phase 9B — Operational Readiness (run_19)

This run completes Phase 9 operational readiness, establishing security sandboxing controls, adversarial injection testing, and automated performance validation checks.

### Things You Must Verify Manually

* **Verification of Adversarial Rejection**: Run the adversarial regression tests:
  ```powershell
  .venv\Scripts\python.exe -m pytest tests/test_code_generator.py -k test_adversarial_prompt_injection_rejected -v
  ```
  Confirm that all simulated malicious injects (eval, imports, page.evaluate, open) are caught and rejected by the validator.
* **Verification of Outbound LLM checks**: Inspect any generated `server.py` in your packages folder. Verify it contains no imports of `litellm` or `groq`, and depends solely on local Playwright actions and FastMCP stdio transport.

### Things You Must Understand

* **AST Sandboxing**: The code validator uses Python's `ast` parsing to analyze the AST structure of LLM responses. Any code structure using loops, conditions, functions/classes definitions, imports, or unapproved methods is automatically rejected.
* **No Runtime Credentials/LLM Outbounds**: To support the "record once, run deterministically forever" architecture, the compiled MCP tool acts as a pure local client driving Playwright. It does not load API keys or call out to any LLM runtime APIs.

### Manual Tasks

1. Run the new adversarial prompt injection test case:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/test_code_generator.py -k test_adversarial_prompt_injection_rejected -v
   ```
2. Run the complete regression suite:
   ```powershell
   .venv\Scripts\python.exe -m pytest tests/ -v
   ```

### Architecture Notes

* **validator.py**: Implements the `DSLSecurityVisitor` which checks every function call and node type against the approved Playwright mini-DSL whitelist.
* **run_benchmark.py**: Dynamically imports compiled tool modules, runs iterations headlessly, and generates markdown reports evaluating latency limits.

### Command Reference

* **Adversarial tests**: `.venv\Scripts\python.exe -m pytest tests/test_code_generator.py -k test_adversarial_prompt_injection_rejected -v`
* **Benchmarking script**: `.venv\Scripts\python.exe scripts/run_benchmark.py --package packages/execute_nobuycart_com --iterations 3`
* **Security auditing**: `.venv\Scripts\python.exe scripts/pii_audit.py --package packages/execute_nobuycart_com`
* **All tests**: `.venv\Scripts\python.exe -m pytest tests/ -v`

### Performance Verification

* Run benchmarking to generate `benchmark_report.md` evaluating the package against the target NFR targets (Generation ≤ 180s, Latency ≤ 20s, Reliability ≥ 90%, PII = 0).

### Diagnostic Reference

* **`pipeline_diagnostics.json`**: Stages status tracking block generated by the pipeline orchestrator. Contains performance duration metrics per compilation step.

---

*Last updated: run_19 — 2026-07-18*

## 20. Phase 10 — BrowserBot v1.0 Release (run_20)

This section details the production release of BrowserBot Version 1.0, outlining system architecture, developer workflows, installation instructions, command references, and troubleshooting.

### Final Architecture Summary

BrowserBot consists of four isolated, decoupled layers that run entirely locally on the operator's machine at $0 marginal cost:
1. **Capture Layer (Recorder & Converter)**: Launches Playwright Codegen browser sessions, converts raw interactive browser commands into parsed schema-compliant Action Logs, and scrubs real-time password entries.
2. **Generalization Layer (Pattern Extractor)**: Runs a local LLM (Ollama/LiteLLM) to extract dynamic input variables and compile user-confirmed parameters.
3. **Compilation Layer (Code Gen & Validator)**: Uses Jinja2 templates and a code-specialized local LLM to generate execution statements, walks AST syntax to sanitize python instructions against security guidelines, and runs headless validation trials.
4. **Integration Layer (Packager & Registry)**: Generates production-ready packages containing self-healing hooks, manifest schemes, timing benchmarks, and registers them directly to Claude Desktop.

### Complete Developer Workflow

```
[Record Play-through] ──► [Parse Action Log] ──► [Generalize / Redact] ──► [DSL Code Compile] ──► [Validate & Sandbox] ──► [Create MCP Package] ──► [Register & Run in Claude]
```

### End-to-End Execution Flow

1. Operator runs `python -m browserbot.recorder start [url]` to capture a workflow.
2. Closing the Chromium window auto-converts the session to `session_<timestamp>.json` and redacts credentials using `scrub()`.
3. Operator runs a script calling `OrchestrationPipeline.run()`.
4. The Pattern Extractor guesses parameters, which the operator accepts/renames via the Confirmer CLI (or auto-approves if `auto_confirm=True`).
5. Code Generator fills in the Jinja2 templates, verifies the result with `validate_dsl()`, and runs a headless validator test.
6. The Packager outputs the bundle directory under `packages/` complete with an installer, package lock, and README documentation.
7. Operator installs the tool using `python -m browserbot.runtime register --package packages/execute_xxx` and restarts Claude Desktop.

### Installation Guide

Ensure you have Python 3.11+ installed. Clone the repository and run:
```powershell
python -m venv .env
.venv\Scripts\pip.exe install -r requirements.txt
playwright install chromium
```
Ensure Ollama is installed and running locally with the target model:
```powershell
ollama pull qwen2.5-coder:7b-instruct-q8_0
```

### Verification Commands

* **Sanity-check Environment**: `.venv\Scripts\python.exe -m browserbot.recorder --demo --headed`
* **Run Regression Tests**: `.venv\Scripts\python.exe -m pytest tests/ -v`
* **Trigger End-to-End Pipeline**: `.venv\Scripts\python.exe run_sample.py`
* **Verify Package Secrets**: `.venv\Scripts\python.exe scripts/pii_audit.py --package packages/execute_nobuycart_com`
* **Run Performance Benchmarks**: `.venv\Scripts\python.exe scripts/run_benchmark.py --package packages/execute_nobuycart_com --iterations 3`
* **Register Server**: `.venv\Scripts\python.exe -m browserbot.runtime register --package packages/execute_nobuycart_com`

### Troubleshooting Guide

* **`ModuleNotFoundError: No module named 'litellm'`**: Ensure you are running Python and pytest using the virtual environment interpreter (`.venv\Scripts\python.exe` and `.venv\Scripts\pytest.exe`).
* **Validation Failure (`overall_success = False`)**: If the compiled tool fails during the validation run, check the failure description and look for a `validation_report.json` in the generated tool's directory. If loading the page is timing out, increase the timeout using the environment variable: `$env:BROWSERBOT_VALIDATOR_TIMEOUT_MS="60000"`.
* **Tool Mismatch in Claude Desktop**: If Claude claims it cannot find the tool, run `python -m browserbot.runtime list` to verify that the server is successfully listed in Claude's configuration file, and restart Claude Desktop completely to refresh the process list.

### Common Pitfalls

* **Typing real credentials during recording**: The recorder writes inputs to script buffers. If you input real credentials, they might get written to raw files before scrubbing. Always use dummy text/test accounts.
* **Deleting source session JSON files**: If the source recording JSON is deleted from `workflows/sessions/`, the package will be unable to run the self-healing algorithm. Always preserve the original recording logs.

### Repository Structure Overview

* `browserbot/`: Core package folder.
  - `recorder/`: Playwright recorder launcher and codegen JSON converter.
  - `agents/`: AI and validation agents (pattern_extractor, code_generator, validator, packager).
  - `runtime/`: Runtime registry, resilience click/fill wrappers, self-healing CLI, and NFR benchmark engine.
  - `models/`: Schema validations and data models.
  - `templates/`: Server template scripts.
* `tests/`: Offline pytest suite verifying validations, parser regexes, PII scrubbing, and mock LLM calls.
* `packages/`: Output folder containing installable, production-ready MCP servers.

### Release Notes (v1.0.0)

* Established robust and local-first architecture running on 100% free local models (Ollama/Groq fallbacks) at $0 Token cost.
* Auto-generates fully sandboxed, AST-compliant, and secure Playwright MCP tools.
* Integrated timing observability, PII scrubbing scans, timing resilience, timing backoff clicks/fills, and self-healing error recovery.
* Automated documentation generation (per-tool README) and performance validation harnesses.

---

*Last updated: run_20 — 2026-07-18*

## 21. Independent Technical Audit (run_21)

This section documents the independent technical audit performed on BrowserBot Version 1.0.

### Overview

An architectural and security audit has verified that the codebase matches the target requirements of Version 1.0, with a clean decoupled design, comprehensive security sandboxing (AST validators), and reliable regression test suites.

### Verification and Results

* **Functional Verification**: The pipeline successfully compiles raw browser play-throughs into structured Action Logs, redacts dynamic inputs, compiles packages, headlessly tests execution, and registers the server with Claude Desktop. During verification, critical bugs with escaped selector quotes and validator secrets redaction were fixed and verified.
* **Security Validation**: Sandboxing controls successfully reject malicious python code payloads. PII scans confirm zero keys leak into the build directories.
* **Test Verification**: All **115 tests** pass successfully in `8.86s` (including new converter tests).

---

*Last updated: run_21 — 2026-07-18*

## 22. Phase v2.1 — Orchestration Server Foundation (run_22)

This section details the FastAPI orchestration server skeleton, SQLite state database, and REST routing endpoints that expose the pipeline steps.

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Start the server: `python -m browserbot.server` and verify it runs on `127.0.0.1:8765` | This is your backend process. The UI single-page application and programmatic clients depend on it. |
| B | Run a health check query: `curl http://127.0.0.1:8765/health` | Smoke-tests that the server is alive and responding with `{"status":"ok"}`. |
| C | Run the new server and DB unit tests: `uv run pytest tests/test_server_db.py tests/test_server_app.py -v` | Confirms the SQLite CRUD operations and REST routing schemas work flawlessly. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Local-Only Binding** | `browserbot/server/config.py` | The server strictly binds to `127.0.0.1` and does not accept external connections to preserve the local-first security NFR. |
| E | **State Store Cache** | `browserbot/server/db.py` | SQLite manages wizard session stage state metadata, but the raw JSON files on disk remain the absolute source of truth. |
| F | **Stage-by-Stage API Facade** | `browserbot/server/routes/` | Exposes endpoints (`extract`, `confirm`, `generate`, `package`, `register`) wrapping the existing CLI pipeline steps 1:1, enabling a wizard client UI. |

### Command Reference

* **Start Orchestration Server**: `python -m browserbot.server`
* **Run Server Tests**: `uv run pytest tests/test_server_db.py tests/test_server_app.py -v`

---

*Last updated: run_22 — 2026-07-18*

## 23. Phase v2.2 — Web UI Wizard (run_23)

This section details the static single-page React client wizard serving as the pipeline presentation layer, routing stages, and interactive parameter editing constraints.

### Things You Must Verify Manually

| # | What to do | Why it matters |
|---|-----------|----------------|
| A | Build React static files: run `npm run build` inside `frontend/` directory | Compiles typescript code and compiles output bundle under `frontend/dist`. |
| B | Access UI: start the FastAPI server (`python -m browserbot.server`) and open `http://127.0.0.1:8765/` | Confirm the 4-stage wizard opens and visualizes recorded sessions, parameters list, validation checks, and installer snippets. |
| C | Run API integrations tests: `uv run pytest tests/test_server_app.py -v` | Confirms the new parameter customization endpoints, manual additions, and name regex verification logic. |

### Things You Must Understand

| # | Concept | Where it is | Why it matters |
|---|---------|-------------|----------------|
| D | **Decoupled Client UI** | `frontend/src/` | The frontend has zero business logic and works solely as a client of the REST API, keeping the backend orchestrator as the single source of truth. |
| E | **Parameter Editing Schema** | `frontend/src/App.tsx` | Implements interactive parameter editing (rename, reject, optional toggles, manual addition) matching the existing CLI confirmer parameters lifecycle exactly. |
| F | **Vite Dev Server Proxy** | `frontend/src/api/client.ts` | The API client automatically directs requests to loopback port `8765` when Vite runs on development ports `5173`/`5174`, simplifying local UI iteration. |

### Command Reference

* **Start UI Dev Server**: `npm run dev` (run inside `frontend/`)
* **Build SPA static bundle**: `npm run build` (run inside `frontend/`)
* **Start Server serving frontend**: `python -m browserbot.server`

---

*Last updated: run_23 — 2026-07-18*










