# run_09 — Phase 4: Manifest Generation + Complete Pipeline Demonstration (Steps 4.3 + 4.4)

## Summary

This batch completes Phase 4 of BrowserBot. The complete end-to-end code generation pipeline was successfully executed:

1. **MCP Tool Manifest Generation (Step 4.3)**: Designed a schema for tool registration description files (`mcp_tool_schema.json`) and implemented a compiler (`manifest.py`) that compiles the `WorkflowSpec` IR into a deterministic `mcp_tool.json` containing the tool name, description, schema, parameter default values, and metadata.
2. **Complete Pipeline Run (Step 4.4)**: Successfully ran the complete generation pipeline (from raw Playwright Action Log recording, through scrubbing, LLM-based parameter extraction, interactive CLI confirmation, IR generation, and LLM-based code generation) to output a compiled stdio FastMCP server and tool manifest.
3. **No manual edits or fixes**: The entire execution was completed autonomously without manually modifying templates or generated output scripts.
4. **All checks passing**: Expanded test suite to **46 passing checks** by adding unit tests for manifest generation and schema validation.

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `docs/schemas/mcp_tool_schema.json` | **NEW** | Draft 2020-12 schema defining the contract for the generated tool manifest (`mcp_tool.json`). |
| `browserbot/models/mcp_tool.py` | **NEW** | Pydantic data models for the manifest (`MCPToolManifest`, `ParametersSchema`, `ParameterProperty`, `ManifestMetadata`) and `MCPToolManifestValidator`. |
| `browserbot/models/__init__.py` | **MODIFIED** | Exposed tool manifest classes in the models namespace. |
| `browserbot/agents/code_generator/manifest.py` | **NEW** | `generate_manifest()` — compiles `WorkflowSpec` IR into `MCPToolManifest` data structures. |
| `browserbot/agents/code_generator/__init__.py` | **MODIFIED** | Exposed `generate_manifest` in the public code_generator package namespace. |
| `browserbot/agents/code_generator/__main__.py` | **MODIFIED** | Integrated manifest generation into the generator CLI wrapper to output `mcp_tool.json` alongside `server.py`. |
| `tests/test_manifest.py` | **NEW** | Unit tests verifying manifest parsing, parameter property schemas, required attributes, and validator rejection. |
| `.env` | **MODIFIED** | Configured `OLLAMA_MODEL_GENERATOR="qwen2.5-coder:7b-instruct-q8_0"` to map to the locally installed code model. |

---

## Pipeline Demonstration

The complete BrowserBot pipeline was run back-to-back:

```
[Browser] --> [Playwright Codegen] --> [session_TIMESTAMP.json] (Raw steps)
                                            |
                                       [scrub()] (PII replacement)
                                            |
                              [session_TIMESTAMP.json] (Scrubbed on disk)
                                            |
                                   [PatternExtractor] (LLM extraction)
                                            |
                                  [confirm_parameters] (CLI Review)
                                            |
                                    [generate_spec]
                                            |
                              [workflow_spec.json] (IR on disk)
                                            |
                                     [CodeGenerator] (LLM code fill)
                                            |
                                     [validate_dsl] (AST Security Visitor)
                                            |
                                      [Jinja2 template]
                                            |
                               [server.py] + [mcp_tool.json] (on disk)
```

1. **Record**: Recorded a session code on `nobuycart.com/tracking/` using:
   ```powershell
   python -m browserbot.recorder start https://nobuycart.com/tracking/
   ```
2. **Extract & Confirm**: Ran the Pattern Extractor with local `llama3:latest` and accepted the extracted parameters via the CLI:
   ```powershell
   python -m browserbot.agents.pattern_extractor --yes --output workflows/sessions/workflow_spec_nobuycart.json workflows/sessions/session_20260716T140748.json
   ```
   *Result*: Persisted `workflow_spec_nobuycart.json` on disk.
3. **Generate**: Invoked the Code Generator using local `qwen2.5-coder:7b-instruct-q8_0` to compile the final script and tool description:
   ```powershell
   python -m browserbot.agents.code_generator --input workflows/sessions/workflow_spec_nobuycart.json --output generated_tools/nobuycart_tracker/
   ```
   *Result*: Generated `server.py` and `mcp_tool.json` successfully under `generated_tools/nobuycart_tracker/`.

---

## Manifest Design

### How Metadata is Derived
Metadata is derived deterministically from the `WorkflowSpec` IR properties without hallucination:
- `mcp_tool_name` is compiled by snake_casing the site hostname (e.g. `execute_nobuycart_com`).
- `description` uses `workflow.description` directly as written during specification.
- `parameters_schema.properties` maps each IR parameter's properties (type = `"string"`, description, default = `example_value`, and `is_sensitive`).
- `parameters_schema.required` lists parameters that are marked `is_optional: false`.
- `metadata` captures the target site, generation timestamp (UTC), generator version, and the source session ID for debug traceability.

### Why Generation is Deterministic
Writing the tool manifest must be completely mechanical. Letting the LLM generate the JSON file introduces formatting bugs (invalid keys, missing required arrays, or hallucinated types) that can cause registration crashes in Claude Desktop or other MCP clients. Standardizing the manifest structure using a JSON schema and Pydantic validation ensures the generated tool description is always parseable.

### Relationship Between `workflow_spec.json` and the Manifest
`workflow_spec.json` represents the **entire workflow spec** (containing raw steps, fixed indices, and locator details) which is used by developers and code engines. 

`mcp_tool.json` is a **downstream, client-facing subset of the spec**. It exposes only the parameters, types, defaults, and tool name so the MCP client can display the tool to the user/LLM and formulate the parameters schema without having to understand page locator details.

---

## Validation Results

- **All tests passing**: Running `python -m pytest tests/` executes **46 tests**, all passing.
- **Generated Python compiles**: The final generated code in `generated_tools/nobuycart_tracker/server.py` compiles successfully without any syntax errors:
  ```powershell
  python -m py_compile generated_tools/nobuycart_tracker/server.py
  ```
- **Generated MCP server starts**: Running the generated script runs the FastMCP stdio server in listening mode:
  ```powershell
  python generated_tools/nobuycart_tracker/server.py
  ```
- **Manifest validates**: Running validation against `mcp_tool_schema.json` passes cleanly with zero errors.

---

## Future Improvements

*Note: These are documented notes only for later exploration, no changes made.*
- **Custom typing in Manifests**: Currently, all tool parameters are treated as type `string`. In the future, we could support typing inference (e.g., `boolean` for checkboxes, `number` for counts) during confirmation UX to allow clients to render richer input interfaces.
- **Dynamic output descriptions**: Describe what outputs are returned (e.g., tracking timeline, current status) in the manifest so the client knows what the tool returns, in addition to its inputs.

---

## Remaining Work (Phase 5 only)

- **Step 5.1**: Build the Dry-Run Harness to programmatically import and call generated tool methods locally (headless).
- **Step 5.2**: Integrate verification checks to auto-trigger validation tests after every generation.

---

## Next Batch

**Recommended: Phase 5 — Validator Agent & Dry-Run Harness**

Deliverables:
1. `browserbot/agents/validator/` package containing the verification agent.
2. `browserbot/runtime/harness.py` to invoke tools directly using example values and check results.
3. Hooking the validator into the CLI to discard broken scripts.

---

*Last updated: run_09 — 2026-07-16*
