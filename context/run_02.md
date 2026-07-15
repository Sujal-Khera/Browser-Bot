# run_02 — Phase 1 Step 1.4 + Phase 2 Step 2.1

## Summary

Two execution-plan steps completed:

- **Step 1.4** — FastMCP "Hello Tool" scaffold: minimal MCP server with one
  static tool (`hello_browserbot`) that returns a fixed string. Validates
  FastMCP plumbing before generation complexity is added.

- **Step 2.1** — Action Log JSON Schema: frozen v1 schema covering all 12
  action types (goto, fill, click, select, check, hover, wait, extract_text,
  extract_attribute, scroll, press_key, screenshot), a hand-crafted example
  recording of the NoBuyCart workflow, and Pydantic models + jsonschema
  validator as the Python-native contract.

Additionally resolved DEV-02 from run_01: removed `anthropic` from
`pyproject.toml`.

---

## Files Changed

| File | Action | Notes |
|------|--------|-------|
| `browserbot/runtime/hello_tool.py` | Created | Step 1.4: FastMCP server, one tool |
| `browserbot/runtime/claude_desktop_config.example.json` | Created | Claude Desktop config snippet |
| `docs/schemas/action_log_schema.json` | Created | Step 2.1: JSON Schema Draft 2020-12 |
| `docs/schemas/action_log_example.json` | Created | Step 2.1: hand-crafted NoBuyCart example |
| `browserbot/models/action_log.py` | Created | Step 2.1: Pydantic models + ActionLogValidator |
| `browserbot/models/__init__.py` | Updated | Re-exports Step 2.1 public API |
| `pyproject.toml` | Updated | DEV-02: removed `anthropic`, updated description |

---

## Validation Results

### Step 1.4 — FastMCP Hello Tool

| Check | Command | Result |
|-------|---------|--------|
| Tool registration | `asyncio.run(mcp.list_tools())` | `[hello_browserbot]` — **PASS** |
| Tool callable | `hello_browserbot()` | `'Hello from BrowserBot! The MCP plumbing works.'` — **PASS** |
| Module importable | `from browserbot.runtime.hello_tool import mcp` | **PASS** |
| Server starts | `python -m browserbot.runtime.hello_tool` | Starts stdio server (manual check) |

**To verify with Claude Desktop:**
1. Copy the config from `browserbot/runtime/claude_desktop_config.example.json`
   into your `claude_desktop_config.json`, updating the `cwd` path.
2. Restart Claude Desktop.
3. Ask: "call the hello browserbot tool"
4. Expected response: `"Hello from BrowserBot! The MCP plumbing works."`

### Step 2.1 — Action Log Schema

| Check | Result |
|-------|--------|
| `action_log_example.json` validates against JSON Schema | **PASS** (0 errors) |
| Pydantic `ActionLog.model_validate(example)` succeeds | **PASS** |
| 7 steps parsed with correct action types | `['goto', 'wait', 'fill', 'click', 'wait', 'extract_text', 'extract_text']` — **PASS** |
| step_index ordering enforced | ValueError on step_index=99 in position 0 — **PASS** |
| PII scrubbing enforced | ValueError when `is_sensitive=True` and value not `__SECRET_*` — **PASS** |
| schema_version Literal["1.0"] | Type-checked at parse time — **PASS** |

---

## Architectural Notes

### AN-01: Hello Tool placement

The hello tool is in `browserbot/runtime/hello_tool.py`. The `runtime/`
package is defined as "the runtime executor for generated MCP tools." The
hello tool scaffolds the exact pattern that generated tools will follow
(FastMCP server + `@mcp.tool` decorator + `mcp.run()`), making it a valid
preview of Phase 6 output, not just a test fixture.

### AN-02: Schema discriminated union strategy

The JSON Schema uses `oneOf` with a `const` on the `action` field as
discriminator. The Pydantic models use `Literal` types on `action` with
`Field(discriminator="action")`. Both sides enforce the same contract
independently — JSON Schema catches malformed files before they reach Python;
Pydantic catches type errors inside the application.

### AN-03: `additionalProperties: false` on all step types

Every step type in the JSON Schema uses `additionalProperties: false`. This
is intentional strictness: if the recorder produces a field the schema
doesn't know about, validation fails loudly. When schema version 2.0 is
needed, the `schema_version` const will be bumped and a new schema file
created — downstream agents can guard with a version check rather than
silently misinterpreting unknown fields.

### AN-04: `allOf` + `additionalProperties` JSON Schema pattern

JSON Schema `allOf` + `additionalProperties: false` requires repeating the
inherited property names in the child schema. This is verbose but necessary
in JSON Schema Draft 2020-12. The alternative (not repeating) would allow
any extra field to pass. All `$ref`-repeated fields exactly match their
parent definitions.

### AN-05: `SelectorInfo.strategy` records locator type

The `strategy` field (`css`, `label`, `role`, `placeholder`, `test_id`, etc.)
is recorded alongside the selector string. This is unused by Phase 2–5 but
was designed for Phase 8 (self-healing selectors), which will use the
strategy metadata to rank selector reliability and generate fallbacks.

### AN-06: `extracted_text` stored at record time

`ExtractTextStep.extracted_text` captures the value at recording time, not
at replay time. This allows the Validator (Phase 5) to diff the replay
output against the ground truth without re-running the page interaction from
scratch. It also gives the Pattern Extractor concrete example values to
reason about when naming parameters.

---

## Known Issues

### KI-01: `hello_tool` cannot be tested end-to-end without Claude Desktop

The FastMCP server runs over stdio transport, which requires a connected MCP
client. Automated testing of the full MCP handshake (tool listing, tool call,
response parsing) is not yet possible without either:
  - Installing Claude Desktop and configuring it (manual step)
  - Using a FastMCP test client (available in FastMCP 3.x via `fastmcp.testing`)

The tool import, registration, and direct function call are all verified
programmatically. The stdio plumbing is structurally correct and identical
to working FastMCP examples.

### KI-02: `action_log_schema.json` uses `"format": "hostname"` for `site`

`jsonschema` does not validate `format` keywords by default unless `format`
checking is enabled (`jsonschema.Draft202012Validator(..., format_checker=...)`).
The `hostname` format on `metadata.site` is therefore not enforced at
runtime. This is acceptable — the schema correctly documents the intent; if
format checking is needed, `jsonschema[format-nongpl]` provides the checker.

### KI-03: `WaitStep.selector` is optional but `wait_for=selector` requires it

The JSON Schema does not enforce that `selector` is present when
`wait_for="selector"`. This constraint is expressible with `if/then` in JSON
Schema but adds significant verbosity. Pydantic validation also does not
enforce it. This is a known gap — if the recorder produces a `wait` step
with `wait_for="selector"` but no `selector`, it will pass schema validation
but fail at replay time. Recommend adding a Pydantic `model_validator` for
this case in Phase 2 when the Recorder is implemented.

---

## Next Batch

**Step 2.2 — Wrap Playwright Codegen as the Recording Mechanism**

From the execution plan:

> Use `playwright codegen --target python -o raw_script.py <url>` under the
> hood, then post-process the generated `.py` script's action calls into your
> JSON schema (parse Playwright's own script output rather than reinventing
> DOM event capture).

Deliverable: `browserbot/recorder/convert_codegen.py` — converts Playwright
codegen output into a valid Action Log JSON file.

Verification: Run the converter on the Step 1.3 NoBuyCart ground-truth flow
and validate the output against `action_log_schema.json`.

Do NOT begin Step 2.3 (Recording UI) until Step 2.2 is complete.

---

*Generated by run_02 — 2026-07-15*
