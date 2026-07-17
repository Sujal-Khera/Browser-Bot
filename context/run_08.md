# run_08 — Phase 4: Deterministic Code Generation (Steps 4.1 + 4.2)

## Summary

This batch implements BrowserBot's deterministic code generation engine. The following milestones were completed:

1. **Static Jinja2 Template (Step 4.1)**: Created the `server.py.j2` template which owns all FastMCP server boilerplate, imports, browser async lifecycle (launch, new context, page, close), logging, exception handling, dynamic tool parameter signatures, and structured output formatting.
2. **Code Generator Agent (Step 4.2)**: Implemented the LLM agent (`generator.py`) and prompt structure (`prompt.py`) that consumes `workflow_spec.json` and emits ONLY safe Playwright interaction statements matching our approved DSL.
3. **AST DSL Validator (Step 4.2 Security Gate)**: Implemented strict static analysis in `validator.py` (`ast.parse` and AST node traversal). It enforces the approved DSL and blocks imports, subprocesses, arbitrary Python execution, filesystem/network library loading, and unauthorized name lookups before template rendering.
4. **All Tests Passing**: Created 11 new tests in `tests/test_code_generator.py` covering DSL allow-lists, security validation, and template rendering. All 44/44 regression checks pass cleanly.

---

## Files Changed

| File | Type | Description |
|------|------|-------------|
| `browserbot/templates/mcp_server_template/server.py.j2` | **NEW** | Hand-crafted static Jinja2 template representing the server boilerplate. |
| `browserbot/agents/code_generator/prompt.py` | **NEW** | Prompt module defining system rules and user prompts for the generator agent. |
| `browserbot/agents/code_generator/validator.py` | **NEW** | AST static analyzer validating generated Playwright statements against the approved DSL. |
| `browserbot/agents/code_generator/generator.py` | **NEW** | `CodeGenerator` — compiles WorkflowSpec IR, calls the generator LLM, validates DSL output, and renders/compiles the script. |
| `browserbot/agents/code_generator/__main__.py` | **NEW** | CLI wrapper for Code Generator (`python -m browserbot.agents.code_generator`). |
| `browserbot/agents/code_generator/__init__.py` | **MODIFIED** | Exposed public classes (`CodeGenerator`, `validate_dsl`, `DSLValidationError`). |
| `tests/test_code_generator.py` | **NEW** | 11 unit tests for security visitor validation and template compilation. |

---

## Generator Architecture

### Template Responsibilities
The hand-crafted Jinja2 template (`server.py.j2`) handles all high-complexity python and library plumbing:
- **FastMCP server registration**: Creating the `FastMCP` instance and applying the `@mcp.tool` decorator with appropriate metadata.
- **Dynamic signatures**: Rendering function arguments based on confirmed parameters from the spec, mapping defaults, and masking sensitive parameters in invocation logs.
- **Playwright lifecycle management**: Launching Chromium, configuring headless/headed mode via environment variables, managing the async browser/context context managers, and closing connections in `finally` clauses.
- **Safety boundaries**: Standardizing try-except-finally blocks to return structured JSON summaries of successes or step errors to the MCP client.
- **Deterministic outputs**: Parsing the spec's `outputs` list and automatically querying `page.locator().inner_text()` at the end of the run to gather returned variables.

### LLM Responsibilities
The LLM's role is narrowed to a single task: translate the linear list of logical spec steps into plain Playwright sequence lines.
- It receives the structured `workflow_spec.json`.
- It outputs plain, un-nested statements like `await page.goto(...)` or `await page.locator(...).click()`.
- It does **not** write any boilerplate, imports, server registration, or output packaging.

### Why the Template is Deterministic
Relying on the LLM to generate the MCP wrapper structure presents significant risks:
- Local models frequently hallucinate library method names (e.g., using old versions of FastMCP or standard MCP syntax).
- Code formatting and indentation errors can break Python compilation.
- The LLM could omit crucial safety operations, such as closing browser connections or redacting sensitive passwords in logging statements.

By locking down the server boilerplate in a deterministic Jinja2 template, we guarantee that the final python script compiles and runs as a valid stdio FastMCP server. The LLM acts solely as a mapping engine for the page steps.

---

## DSL Design

### Allowed Statements
The DSL restricts calls to a safe subset of standard Playwright actions:
- Chained locator calls: `page.locator()`, `page.get_by_role()`, `page.get_by_label()`, `page.get_by_placeholder()`, `page.get_by_text()`, `page.get_by_test_id()`.
- Sequential page actions: `goto()`, `wait_for_selector()`, `wait_for_timeout()`.
- Chained operations: `fill()`, `click()`, `press()`, `text_content()`, `inner_text()`.

### Rejected Statements
Any code blocks containing the following are immediately blocked by the AST Validator before template compilation:
- **Imports**: `import ...` or `from ... import ...` (blocks loading socket, urllib, os, sys, etc.)
- **Execution wrappers**: Calls to `eval()`, `exec()`, `compile()`.
- **System and FS access**: Calls to `open()`, `subprocess`, `print()`, `input()`.
- **Flow Control & Declarations**: Statements defining `def`, `class`, loops (`for`, `while`), `if` blocks, and `try` blocks.
- **Arbitrary Python**: Loads of any names not defined as variables (i.e. parameters from the spec, local variables assigned from text queries, or the `page` variable).

### Security Reasoning
Restricting the generated code block to a strictly linear sequence of Playwright API statements ensures that even a compromised or misbehaving LLM cannot write code that accesses the host file system, executes shell commands, connects to arbitrary network domains, or leaks credentials. If any such AST node is discovered, it is caught at the boundary and rejected, raising `DSLValidationError`.

---

## Validation Results

- **All tests passing**: Running `python -m pytest tests/` executes **44 tests**, all passing.
- **Template compiled successfully**: Renders the complete stdio server, which passes compile-check successfully:
  ```powershell
  python -m py_compile generated_tools/check_order_status/server.py
  ```
- **CLI end-to-end dry-run**: Running the generator CLI against `workflow_spec_nobuycart.json` outputs a valid and fully-operational FastMCP server body.

---

## Remaining Work (Phase 4 only)

- **Step 4.3**: Implement the MCP Tool Manifest auto-generation (`mcp_tool.json`) to register tool names, descriptions, and schemas.
- **Step 4.4**: First full pipeline test run (Log -> Spec -> Server) with zero manual edits.

---

## Next Batch

**Recommended: Phase 4 (Steps 4.3 + 4.4) - Tool Manifest & End-to-End Pipeline Verification**

Deliverables:
1. `browserbot/agents/code_generator/manifest.py` to compile tool manifests from WorkflowSpec.
2. An orchestration entry point/script (`browserbot/orchestrator/`) mapping Phase 2 (Record) -> Phase 3 (Extract & Confirm) -> Phase 4 (Generate & Manifest) into a single unified pipeline.
3. Live end-to-end verification (5 execution runs) testing the generated server.

---

*Last updated: run_08 — 2026-07-16*
