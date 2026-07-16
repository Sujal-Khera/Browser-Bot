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
