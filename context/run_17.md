# run_17 — Phase 8B: Adaptive Selector Recovery

## Summary

This batch completes Phase 8 (Resilience) of the execution plan by implementing Step 8.3 (Basic Self-Healing) and Step 8.4 (Network & Timing Resilience).

1. **Timing & Network Resilience (Step 8.4)**:
   - Added explicit waits (`wait_for_load_state("networkidle")`) inside the locator resolution routine in [resilience.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/runtime/resilience.py) to prevent dynamic/slow rendering race conditions.
   - Designed action execution wrappers `resilient_click` and `resilient_fill` implementing exponential retry-with-backoff algorithms (delays of `0.1s`, `0.5s`, `1.0s`, and `2.0s`) around locator resolution and action execution.
2. **Resilience Integration**:
   - Whitelisted `"resilient_click"` and `"resilient_fill"` as allowed methods/variables in the static AST validator in [validator.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/agents/code_generator/validator.py).
   - Updated dry-run generator [generator.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/agents/code_generator/generator.py) to output these wrappers for click and fill workflow steps.
3. **Basic Self-Healing (Step 8.3)**:
   - Updated generated tool template [server.py.j2](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/templates/mcp_server_template/server.py.j2) to catch workflow execution exceptions and write a `needs_healing.flag` file inside the tool package directory.
   - Built a programmatic self-healing routine `self_heal_package` inside [self_healing.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/orchestrator/self_healing.py). It reads the package manifest, locates the matching raw recorded session log in `workflows/sessions/`, and re-runs the entire orchestrator compilation, validation, packaging, and Claude registration pipeline. Upon successful validation, it deletes the `needs_healing.flag` file.
   - Exposed a `self-heal` CLI subcommand in `browserbot/runtime/__main__.py`.
4. **All Tests Passing**: Added new tests in [test_self_healing.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/tests/test_self_healing.py) covering resilient retry logic and package self-healing routines. All **107 regression and resilience tests** pass cleanly in `8.65s`.

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| [browserbot/runtime/resilience.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/runtime/resilience.py) | **MODIFIED** | Added `networkidle` settling check and whitelisted wrappers `resilient_click` and `resilient_fill` with backoffs. |
| [browserbot/runtime/__init__.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/runtime/__init__.py) | **MODIFIED** | Exports `resilient_click` and `resilient_fill` in runtime namespace. |
| [browserbot/agents/code_generator/generator.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/agents/code_generator/generator.py) | **MODIFIED** | Compiles click and fill steps using `resilient_click` and `resilient_fill` wrappers. |
| [browserbot/agents/code_generator/validator.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/agents/code_generator/validator.py) | **MODIFIED** | Whitelists `resilient_click` and `resilient_fill` in AST validator allowed variables. |
| [browserbot/templates/mcp_server_template/server.py.j2](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/templates/mcp_server_template/server.py.j2) | **MODIFIED** | Imports timing wrappers. Catch block writes `needs_healing.flag` file to package directory on runtime failure. |
| [browserbot/orchestrator/self_healing.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/orchestrator/self_healing.py) | **NEW** | Programmatic self-healing routine locating session logs and triggering validation compiles. |
| [browserbot/orchestrator/__init__.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/orchestrator/__init__.py) | **MODIFIED** | Exports `self_heal_package` function. |
| [browserbot/runtime/__main__.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/browserbot/runtime/__main__.py) | **MODIFIED** | Implements `self-heal` CLI subcommand with package and force flags. |
| [tests/test_self_healing.py](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/tests/test_self_healing.py) | **NEW** | Unit tests verifying action retry limits and self-healing pipelines. |
| [context/run_17.md](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/context/run_17.md) | **NEW** | This report documenting Phase 8B timing resilience and self-healing architecture. |
| [context/ORIENTATION.md](file:///c:/Users/hp/OneDrive/Desktop/BrowserBot/context/ORIENTATION.md) | **MODIFIED** | Appended run_17 timing resilience and self-healing references and commands. |

---

## Phase 8B Architecture

The runtime timing resilience and self-healing systems interact seamlessly:

```
        [ Claude Desktop / User Invocation ]
                         │
                         ▼
        [ Generated FastMCP Server execution ]
                         │
        ┌────────────────┴────────────────┐
        ▼ (Success)                       ▼ (Exception)
[ Return success prose ]         [ Write needs_healing.flag ]
                                          │
                                          ▼
                                 [ Trigger Self-Heal ]
                                          │
                                          ▼
                               [ Resolve Session ID ]
                                          │
                                          ▼
                             [ Re-run Orchestration Pipeline ]
```

---

## Recovery Strategy

- **Graceful Degradation**: If an action fails (due to element overlap, dynamic CSS class shifts, or lazy rendering delays), BrowserBot does not abort. It pauses, backs off, and re-polls the prioritized candidates list.
- **Self-Healing Loop**: If a previously working tool permanently fails (e.g., due to a major site structural change), it flags itself by writing `needs_healing.flag`. The self-healing CLI subcommand reads this flag, re-fetches the original raw recorded log, and re-compiles the tool to adapt to the new selectors.

---

## Selector Resolution Pipeline

1. **Load Settle**: Invokes `wait_for_load_state("networkidle")` before element resolution.
2. **Prioritized Matching**: Sequential candidate locator evaluation (Aria -> Label -> Placeholder -> Test ID -> Text -> CSS/XPath).
3. **Execution Retry**: Exponential backoff delay retry loops (`0.1s` -> `0.5s` -> `1.0s` -> `2.0s`) around actions.
4. **Defers to Playwright**: If all fallbacks time out, delegates to standard Playwright locators to raise tracebacks and capture screenshot diagnostics.

---

## Validation Results

- **All Tests Pass**: Running `.venv\Scripts\python.exe -m pytest tests/` executes **107 tests** successfully.
- **CLI Self-Healing Execution**: Running:
  ```powershell
  .venv\Scripts\python.exe -m browserbot.runtime self-heal --package packages/execute_nobuycart_com --force
  ```
  runs successfully, resolving the original session log from metadata, re-compiling, and registering the tool.

---

## Compatibility Notes

- **Zero Schema Changes**: Completed without modifying the underlying Intermediate Representation (IR) schemas or JSON specifications.
- **Backward Compatibility**: Direct Playwright locator statements in previously generated tools remain functional and pass AST whitelisting checks.

---

## Bugs Fixed

- None.

---

## Future Improvements
*(Documentation Only)*

- **Telemetry on Re-Run**: Record self-healing metrics (number of self-heals, modified selectors list) inside the diagnostics file.

---

## Phase 8 Completion Checklist

| Task | Description | Status |
|------|-------------|--------|
| Step 8.1 | Robust Selector Strategy | ✅ Complete |
| Step 8.2 | Second-Site Generalization | ✅ Complete |
| Step 8.3 | Basic Self-Healing | ✅ Complete |
| Step 8.4 | Network & Timing Resilience | ✅ Complete |

**Phase 8 is fully complete.**

---

## Remaining Work

Only Phase 9 (Security, Privacy & QA Hardening) onward.

---

*Last updated: run_17 — 2026-07-17*
