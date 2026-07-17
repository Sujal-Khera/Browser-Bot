# run_07 — Phase 3: Edge Cases + Intermediate Representation (Steps 3.3 + 3.4)

## Summary

This batch completes the Pattern Extraction pipeline. The following goals were accomplished:

1. **Edge Case Handling (Step 3.3)**: System updated to handle zero parameters, one parameter, multiple parameters, repeated parameters, and optional parameters without modifying previous behaviour. Created three test fixtures mapping directly to these edge cases.
2. **Intermediate Representation Output (Step 3.4)**: Compiles the validated `ActionLog` and user-confirmed parameters into a canonical, versioned JSON spec (`workflow_spec.json`). This IR serves as a clean, Playwright-independent abstraction layer.
3. **Pydantic Data Models**: Implemented Pydantic models for the IR (`WorkflowSpec`) and a schema validator (`WorkflowSpecValidator`) mirroring the Action Log validation pattern for consistency.
4. **All tests passing**: Automated test suite expanded to 33 checks, covering the new edge cases and IR generation logic. Successfully tested IR generation against the ground-truth NoBuyCart recording.

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `docs/schemas/workflow_spec_schema.json` | **NEW** | Draft 2020-12 schema defining the contract for the IR (`workflow_spec.json`). |
| `docs/schemas/extractor_output_schema.json` | **MODIFIED** | Added `is_optional` flag to the parameter schema. |
| `browserbot/models/workflow_spec.py` | **NEW** | Pydantic data models for the IR (`WorkflowSpec`, `IRParameter`, `IROutput`, `WorkflowMetadata`, `WorkflowInfo`) and `WorkflowSpecValidator`. |
| `browserbot/models/__init__.py` | **MODIFIED** | Exposed workflow spec models in the public namespace. |
| `browserbot/agents/pattern_extractor/generator.py` | **NEW** | `generate_workflow_spec()` — compiles `ActionLog` + `ConfirmedOutput` into `WorkflowSpec`. |
| `browserbot/agents/pattern_extractor/confirmer.py` | **MODIFIED** | Added choice `[o]` to mark parameters optional. Added optional prompting when manually adding parameters. |
| `browserbot/agents/pattern_extractor/prompt.py` | **MODIFIED** | Added `is_optional` property to prompt schema excerpt. |
| `browserbot/agents/pattern_extractor/models.py` | **MODIFIED** | Added `is_optional` to `ExtractedParameter` data model. |
| `browserbot/agents/pattern_extractor/__init__.py` | **MODIFIED** | Exposed `generate_workflow_spec` in the package init. |
| `browserbot/agents/pattern_extractor/__main__.py` | **MODIFIED** | Integrated spec generator into CLI. Added `--output` parameter. Writes `workflow_spec.json` on completion. |
| `tests/fixtures/session_zero_params.json` | **NEW** | Fixture: 0-parameter workflow log. |
| `tests/fixtures/session_zero_params_expected.json` | **NEW** | Expected extractor output for zero-parameter fixture. |
| `tests/fixtures/session_single_param.json` | **NEW** | Fixture: 1-parameter search log. |
| `tests/fixtures/session_single_param_expected.json` | **NEW** | Expected extractor output for single-parameter fixture. |
| `tests/fixtures/session_multi_params.json` | **NEW** | Fixture: Multi-parameter signup log (sensitive, repeated, and optional inputs). |
| `tests/fixtures/session_multi_params_expected.json` | **NEW** | Expected extractor output for multi-parameter fixture. |
| `tests/test_pattern_extractor.py` | **MODIFIED** | Appended 3 automated edge case integration tests verifying IR generation correctness and validation. |

---

## Intermediate Representation Design

### Why the IR exists

In complex AI systems, generating execution code directly from a raw transcript or log mixes two different concerns:
1. **Semantic Understanding**: Deciding *what* the user wants to accomplish (e.g. what inputs are variables, what needs to be extracted, which steps are fixed).
2. **Code Generation**: Translating those logical intentions into syntactically valid code (e.g. Playwright browser setup, selector mapping, exception handling).

The Intermediate Representation (IR) acts as the **decoupling boundary** between these concerns. The Pattern Extractor (Phase 3) handles semantic understanding and outputs a `workflow_spec.json`. The Code Generator (Phase 4) reads `workflow_spec.json` and produces the runnable server. 

### Why the IR is independent from Playwright

The IR is a **logical model of the workflow**, not a Playwright script wrapper. It defines:
- Inputs (types, example values, sensitivity, optionality)
- Steps (actions, selector targets, parameter bindings)
- Outputs (elements to extract, target output variable names)

It has **no concept of**:
- Playwright syntax (`page.goto()`, `page.fill()`, locators)
- MCP boilerplate (`FastMCP`, `@mcp.tool()`, servers)
- Python implementation details (imports, try/except blocks)

Because the IR is independent, we can easily change our downstream target (e.g., swapping Playwright for Selenium, or generating a standard HTTP API client instead of an MCP tool) by simply writing a new code generator without changing any recording or pattern-extraction code.

### Why it becomes the contract for Phase 4

By isolating the LLM reasoning (Phase 3) from boilerplate code generation (Phase 4), we establish a **strict API contract**:
1. **Mockability**: Phase 4's Code Generator can be unit-tested using mock `workflow_spec.json` files without needing to run Ollama or the browser.
2. **Determinism**: Since the IR represents a structured logical intent, the generator can use static Jinja2 templates for FastMCP boilerplate and only ask a code-focused LLM (e.g. Qwen2.5-Coder) to translate step structures into simple sequential statements.
3. **Safety**: Phase 4 only has to generate actions matching the steps defined in the IR. Any attempt by the generator LLM to output arbitrary code can be validated against the IR sequence, preventing prompt-injection attacks from running unauthorized commands.

---

## Validation Results

### Test Execution

All 33 unit tests passed successfully. No regressions were observed.

```powershell
python -m pytest tests/ -v
```

| Suite | Status | Total Checks | Description |
|-------|--------|--------------|-------------|
| `test_pattern_extractor.py` | **PASS** | 20 | Extractor edge cases, retry logs, confirmer CLI, and IR spec validation |
| `test_scrubber.py` | **PASS** | 13 | PII/Secret scrubbing checks and immutability invariants |

### Pipeline Validation

Ran the complete pipeline against the ground-truth session:
```powershell
python -m browserbot.agents.pattern_extractor --yes --output workflows/sessions/workflow_spec_nobuycart.json workflows/sessions/session_20260716T140748.json
```
- Local Ollama running `llama3:latest` completed parameter extraction successfully.
- Correctly identified parameter `fake_order_code` as dynamic.
- Correctly marked `fake_order_code` as optional (`is_optional: true`).
- Compiled into a valid `WorkflowSpec` IR matching `workflow_spec_schema.json` and successfully wrote to `workflow_spec_nobuycart.json`.

---

## Known Limitations

| Limitation | Severity | Impact | Mitigation |
|------------|----------|--------|------------|
| Step-level selectors are raw copies from the Action Log | Low | Code Generator must parse the selector details | Handled by code generator templates/logic in Phase 4. |
| Time offsets are stored as float offsets, not logical steps | Low | Generated script contains hardcoded pauses if needed | Phase 4 can compile actions sequentially; slow-motion settings in Settings can manage delays globally. |
| ExtractText value validation not verified on spec output | Low | Replay output variables are unverified in this phase | The Validator (Phase 5) will assert runtime extraction matches against these spec output structures. |

---

## Remaining Work (Phase 4 only)

The following steps compose the next phase of the execution plan:

- **Step 4.1**: Build the FastMCP Server Jinja2 template (`templates/mcp_server_template/server.py.j2`).
- **Step 4.2**: Implement the Code Generator LLM agent (mapping spec steps to permitted sequence statement blocks).
- **Step 4.3**: Generate the MCP Tool Manifest (`mcp_tool.json` or native FastMCP parameters).
- **Step 4.4**: First full codegen run (Log -> Spec -> Server) with zero manual edits, running end-to-end.

---

## Next Batch

**Recommended: Phase 4 — Code Generation Engine**

Deliverables:
1. Jinja2 template for a secure FastMCP server.
2. `browserbot/agents/code_generator/` implementation using a code-specialized model (e.g. Qwen2.5-Coder) via LiteLLM to render the action sequence.
3. Automated compilation check (`py_compile` + AST validation to block non-Playwright calls).

---

*Generated by run_07 — 2026-07-16*
