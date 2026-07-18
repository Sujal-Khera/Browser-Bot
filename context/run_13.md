# run_13 — Phase 6: Registry & Result Formatting (Steps 6.3 + 6.4)

## Summary

This batch completes Phase 6 — BrowserBot's Claude Desktop integration and result formatting pipeline.

1. **Claude Desktop Registry (Step 6.3)**: Implemented `ClaudeDesktopRegistry` in `browserbot/runtime/registry.py`. Reads the platform-appropriate Claude Desktop config file, merges the BrowserBot package entry into `mcpServers` non-destructively (never removes existing servers), creates a timestamped backup before writing, and supports dry-run mode for safe review. Cross-platform (Windows/macOS/Linux) via `platform.system()` + `%APPDATA%`. CLI exposed at `python -m browserbot.runtime register|unregister|list`.

2. **Result Formatting (Step 6.4)**: Extracted result formatting into a standalone, fully unit-testable module `browserbot/runtime/result_formatter.py` with two public functions:
   - `format_success(outputs: dict) -> str`: Converts extraction outputs to conversational prose (e.g. `"• Order Status: Delivered"`) that Claude can relay verbatim. Never returns raw JSON.
   - `format_error(exc_message: str) -> str`: Converts raw exception text to a clean, user-friendly error sentence. Strips Python tracebacks, verbose prefixes, and class names. Always starts with `"I wasn't able to complete the workflow"` (sentinel used by `DryRunHarness`).

3. **Template Updated**: The Jinja2 template `server.py.j2` now imports `format_success` / `format_error` from `result_formatter`. The template no longer returns raw JSON to Claude — all tool returns are prose.

4. **Harness + Pipeline Updated**: `DryRunHarness` now detects error returns via the sentinel phrase instead of JSON parsing. `ValidationPipeline` Stage 5 now validates prose output by checking that expected output labels (snake_case → Title Case) appear in the prose.

5. **All tests passing**: 89 regression checks pass, up from 61 in run_12. New suites: `test_registry.py` (10 tests) and `test_result_formatting.py` (18 tests).

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `browserbot/runtime/registry.py` | **NEW** | `ClaudeDesktopRegistry` class — register/unregister/list/is_registered |
| `browserbot/runtime/__main__.py` | **NEW** | CLI entry point — `register`, `unregister`, `list` subcommands |
| `browserbot/runtime/result_formatter.py` | **NEW** | `format_success()` and `format_error()` — result formatting module |
| `browserbot/runtime/__init__.py` | **MODIFIED** | Exposed registry and formatter in package namespace |
| `browserbot/templates/mcp_server_template/server.py.j2` | **MODIFIED** | Imports `format_success`/`format_error`; no longer returns raw JSON |
| `browserbot/agents/validator/harness.py` | **MODIFIED** | Detects error returns via sentinel phrase instead of JSON parsing |
| `browserbot/agents/validator/pipeline.py` | **MODIFIED** | Stage 5 validates prose output labels instead of JSON keys |
| `tests/test_registry.py` | **NEW** | 10 tests covering registry create/merge/overwrite/dry-run/backup/unregister/list |
| `tests/test_result_formatting.py` | **NEW** | 18 tests covering success prose, error prose, sentinel match, never-raises |
| `tests/test_validator.py` | **MODIFIED** | Updated mocks for prose return contract |
| `tests/test_code_generator.py` | **MODIFIED** | Updated stale `import json` assertion to `from browserbot.runtime.result_formatter` |

---

## Registry Architecture

```
python -m browserbot.runtime register --package packages/execute_nobuycart_com
                ↓
   ClaudeDesktopRegistry.register(package)
                ↓
   _load_config()       → %APPDATA%\Claude\claude_desktop_config.json
   _backup_config()     → claude_desktop_config.20260717T093000.bak.json
   existing["mcpServers"]["execute_nobuycart_com"] = snippet
   _write_config(merged) → writes updated JSON
                ↓
   ✅ Tool registered.  Restart Claude Desktop.
```

### Dry-run output (verified)
```
[dry-run] The following entry would be written to:
  C:\Users\<username>\AppData\Roaming\Claude\claude_desktop_config.json

{
  "mcpServers": {
    "execute_nobuycart_com": {
      "command": "python",
      "args": ["C:\\...\\packages\\execute_nobuycart_com\\server.py"],
      "env": {"BROWSERBOT_HEADLESS": "true"}
    }
  }
}
```

---

## Result Formatting Contract (Step 6.4)

| Path | Tool returns to Claude | Harness detection |
|------|----------------------|-------------------|
| **Success** | `"The workflow completed successfully.\n• Order Status: Delivered"` | Non-sentinel, non-empty string |
| **Error** | `"I wasn't able to complete the workflow right now. Reason: …"` | Starts with `_ERROR_SENTINEL` |

- `format_error` strips: `"Workflow execution failed: "`, `"TimeoutError: "`, full tracebacks
- Both functions are belt-and-suspenders: never raise even on `None` input
- Sentinel constant lives in `result_formatter.py` — changing it requires updating `harness.py` too (documented)

---

## Validation Results

```
python -m pytest tests/ -v
89 passed in 5.96s
```

| Suite | Tests | Status |
|-------|-------|--------|
| `test_code_generator.py` | 11 | ✅ |
| `test_manifest.py` | 2 | ✅ |
| `test_packager.py` | 6 | ✅ |
| `test_pattern_extractor.py` | 20 | ✅ |
| `test_registry.py` | 10 | ✅ NEW |
| `test_result_formatting.py` | 18 | ✅ NEW |
| `test_retry_loop.py` | 3 | ✅ |
| `test_scrubber.py` | 13 | ✅ |
| `test_validator.py` | 6 | ✅ |

---

## Manual Steps Remaining (for Human Operator)

### Step 6.3 — Completing the actual Claude Desktop registration

The code is ready. To complete the live registration:

```powershell
# 1. Register the package (writes claude_desktop_config.json)
.venv\Scripts\python.exe -m browserbot.runtime register `
    --package packages\execute_nobuycart_com

# 2. Restart Claude Desktop

# 3. In a fresh Claude chat, type:
"Check my order status for order code NBC-2026-E3ZXJC"

# 4. Repeat with paraphrased questions:
"Did my package ship? My order is NBC-2026-E3ZXJC"
"Track order NBC-2026-E3ZXJC for me"
"What's the delivery status of NBC-2026-E3ZXJC?"
```

Expected: Claude Desktop selects and invokes `execute_nobuycart_com`, runs the Playwright workflow, and relays the prose result in the chat.

### Step 6.4 — Verifying error surfacing

```powershell
# To verify the error path, deliberately break the server URL:
# Edit packages\execute_nobuycart_com\server.py line 49
# Change: await page.goto("https://nobuycart.com/tracking/")
# To:     await page.goto("https://this-site-does-not-exist.invalid/")
# Then ask Claude the question — it should reply with a clean error message,
# not a Python traceback.
```

---

## Known Limitations

| Limitation | Severity | Impact |
|------------|----------|--------|
| Registry writes absolute `server.py` path — if package is moved, re-run packager | Low | Re-register after moving |
| Error sentinel is a plain string constant — must stay in sync between `result_formatter.py` and `harness.py` | Low | Documented in both files |
| Registry does not detect/update if Claude Desktop is currently running | Low | User must restart Claude Desktop after registration |

---

## Phase 6 — Completion Status

| Step | Description | Status |
|------|-------------|--------|
| 6.1 | Package as an installable MCP/Desktop Extension | ✅ Done (run_12) |
| 6.2 | Local Install & Registration Test | ✅ Done (run_12) |
| 6.3 | Natural-Language Invocation (registry code) | ✅ Done (run_13) |
| 6.4 | Result Formatting & Error Surfacing | ✅ Done (run_13) |

**Phase 6 is code-complete.** The live Claude Desktop invocation test (showing the actual chat exchange) is a manual human step per the execution plan.

---

## Next Batch

**Recommended: Phase 7 — Orchestration UI & End-to-End UX Polish**

Deliverables:
1. Minimal local web page (Flask/FastAPI) with 4 stages: Record → Confirm Parameters → Generate & Validate → Install
2. Progress visualization (live log/screenshot streaming during validation)
3. Explicit UI error states for every failure mode

---

*Generated by run_13 — 2026-07-17*
