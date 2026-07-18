"""
tests/test_code_generator.py — Phase 4: Code Generator Agent and DSL Validator tests.

Runs offline without Ollama or external dependencies by using dry-run mode
and unittest.mock.

Run:
    python -m pytest tests/test_code_generator.py -v
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.agents.code_generator.validator import (
    DSLValidationError,
    validate_dsl,
)
from browserbot.models.workflow_spec import WorkflowSpec

# Fixtures path
FIXTURE_ZERO = Path(__file__).parent / "fixtures" / "session_zero_params.json"
FIXTURE_SINGLE = Path(__file__).parent / "fixtures" / "session_single_param.json"
FIXTURE_MULTI = Path(__file__).parent / "fixtures" / "session_multi_params.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_spec_from_session(path: Path, parameters: list, fixed_indices: list, desc: str = "Test workflow") -> WorkflowSpec:
    """Helper to mock a WorkflowSpec directly from a session fixture log."""
    from browserbot.models.action_log import ActionLog
    from browserbot.agents.pattern_extractor.generator import generate_workflow_spec
    from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput
    
    from browserbot.agents.pattern_extractor.models import ExtractedParameter

    log = ActionLog.from_file(path)
    extracted_params = []
    for p in parameters:
        if isinstance(p, dict):
            extracted_params.append(ExtractedParameter(**p))
        else:
            extracted_params.append(p)

    confirmed = ConfirmedOutput(
        parameters=extracted_params,
        fixed_step_indices=fixed_indices,
        workflow_description=desc,
    )
    return generate_workflow_spec(log, confirmed)


# ---------------------------------------------------------------------------
# Test 1: Code Generator accepts WorkflowSpec (dry-run)
# ---------------------------------------------------------------------------


def test_generator_accepts_spec_dry_run() -> None:
    spec = _load_spec_from_session(FIXTURE_ZERO, [], [0, 1], "Zero parameters workflow")
    generator = CodeGenerator(dry_run=True)
    result = generator.generate(spec)
    
    assert isinstance(result, str)
    assert "FastMCP" in result
    assert "run_workflow" in result
    
    # Ensure generated code compiles successfully
    ast.parse(result)


# ---------------------------------------------------------------------------
# Test 2: Renders correct boilerplate and imports
# ---------------------------------------------------------------------------


def test_generator_renders_boilerplate_and_imports() -> None:
    spec = _load_spec_from_session(FIXTURE_SINGLE, [
        {"name": "search_input", "example_value": "hello", "log_step_index": 1, "is_sensitive": False}
    ], [0, 2], "Search workflow")
    
    generator = CodeGenerator(dry_run=True)
    result = generator.generate(spec)
    
    # Essential imports
    assert "from fastmcp import FastMCP" in result
    assert "from playwright.async_api import async_playwright" in result
    # Step 6.4: template now imports from result_formatter instead of json
    assert "from browserbot.runtime.result_formatter import format_success, format_error" in result

    # FastMCP server registration and setup
    assert "mcp = FastMCP(" in result
    assert "@mcp.tool" in result
    assert 'async def run_workflow(\n    search_input: str = "hello",\n)' in result
    assert 'mcp.run()' in result


# ---------------------------------------------------------------------------
# Test 3: DSL Validator accepts legal Playwright statements
# ---------------------------------------------------------------------------


def test_dsl_validator_accepts_legal_code() -> None:
    legal_code = """
await page.goto("https://example.com")
await page.get_by_role("textbox", name="Username").fill(user_val)
await page.get_by_role("button", name="Submit").click()
await page.wait_for_selector("div.results", state="visible")
await page.wait_for_timeout(1500)
    """
    # Validation passes without error
    validate_dsl(legal_code, allowed_variables={"user_val"})


# ---------------------------------------------------------------------------
# Test 4: DSL Validator rejects forbidden imports
# ---------------------------------------------------------------------------


def test_dsl_validator_rejects_imports() -> None:
    bad_code_1 = "import os\nawait page.goto('https://example.com')"
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl(bad_code_1)
    assert "Imports are strictly forbidden" in str(exc.value)

    bad_code_2 = "from sys import exit\nawait page.goto('https://example.com')"
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl(bad_code_2)
    assert "Imports are strictly forbidden" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 5: DSL Validator rejects functions and classes
# ---------------------------------------------------------------------------


def test_dsl_validator_rejects_definitions() -> None:
    bad_code_1 = "def helper():\n    pass\nawait page.goto('https://example.com')"
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl(bad_code_1)
    assert "Function definitions are forbidden" in str(exc.value)

    bad_code_2 = "class Danger:\n    pass\nawait page.goto('https://example.com')"
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl(bad_code_2)
    assert "Class definitions are forbidden" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 6: DSL Validator rejects control structures (loops, conditionals)
# ---------------------------------------------------------------------------


def test_dsl_validator_rejects_control_structures() -> None:
    # If blocks
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl("if True:\n    await page.goto('https://example.com')")
    assert "Conditional statements" in str(exc.value)

    # For loops
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl("for i in range(10):\n    await page.goto('https://example.com')")
    assert "Loops (for)" in str(exc.value)

    # While loops
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl("while True:\n    await page.goto('https://example.com')")
    assert "Loops (while)" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 7: DSL Validator rejects dangerous builtins and libraries
# ---------------------------------------------------------------------------


def test_dsl_validator_rejects_dangerous_calls() -> None:
    # eval
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl("eval('page.goto(url)')")
    assert "Forbidden function call 'eval'" in str(exc.value)

    # open
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl("f = open('secrets.txt')")
    assert "Forbidden function call 'open'" in str(exc.value)

    # print
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl("print('log message')")
    assert "Forbidden function call 'print'" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 8: DSL Validator rejects non-DSL Playwright methods
# ---------------------------------------------------------------------------


def test_dsl_validator_rejects_non_dsl_methods() -> None:
    # page.evaluate is NOT in the approved Playwright DSL list
    bad_code = "await page.evaluate('() => document.title')"
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl(bad_code)
    assert "Playwright method 'evaluate' is not in the approved DSL" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 9: DSL Validator rejects unassigned/unauthorized local names
# ---------------------------------------------------------------------------


def test_dsl_validator_rejects_unauthorized_variables() -> None:
    # custom_variable is not in allowed_variables and not assigned local variable
    bad_code = "await page.goto(custom_variable)"
    with pytest.raises(DSLValidationError) as exc:
        validate_dsl(bad_code)
    assert "Use of unauthorized variable 'custom_variable'" in str(exc.value)


# ---------------------------------------------------------------------------
# Test 10: Code Generator LLM validation retry loop (success)
# ---------------------------------------------------------------------------


def test_generator_retry_loop_succeeds_on_second_attempt() -> None:
    spec = _load_spec_from_session(FIXTURE_SINGLE, [
        {"name": "search_input", "example_value": "hello", "log_step_index": 1, "is_sensitive": False}
    ], [0, 2], "Search workflow")
    
    call_count = {"n": 0}
    
    def fake_call(messages, *args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First attempt outputs dangerous code (import)
            return "import os\nawait page.goto('https://example.com')"
        # Second attempt outputs clean valid DSL statements
        return "await page.goto('https://example.com')\nawait page.get_by_label('Search input').fill(search_input)"

    with patch(
        "browserbot.agents.code_generator.generator._call_llm",
        side_effect=fake_call,
    ):
        generator = CodeGenerator(dry_run=False, backend="ollama", max_retries=1)
        result = generator.generate(spec)

    assert call_count["n"] == 2
    assert "from fastmcp import FastMCP" in result
    assert "await page.goto('https://example.com')" in result
    ast.parse(result)


# ---------------------------------------------------------------------------
# Test 11: Code Generator LLM validation retry loop (exhaustion)
# ---------------------------------------------------------------------------


def test_generator_retry_loop_raises_when_exhausted() -> None:
    spec = _load_spec_from_session(FIXTURE_SINGLE, [
        {"name": "search_input", "example_value": "hello", "log_step_index": 1, "is_sensitive": False}
    ], [0, 2], "Search workflow")
    
    def always_bad(messages, *args, **kwargs):
        # Always output forbidden conditional control
        return "if True:\n    await page.goto('https://example.com')"

    with patch(
        "browserbot.agents.code_generator.generator._call_llm",
        side_effect=always_bad,
    ):
        generator = CodeGenerator(dry_run=False, backend="ollama", max_retries=1)
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate(spec)
            
    assert "Code generation failed after 2 attempt(s)" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 12: Adversarial prompt injection containing malicious code is rejected
# ---------------------------------------------------------------------------


def test_adversarial_prompt_injection_rejected() -> None:
    """
    Verifies that adversarial prompt injection returning malicious/arbitrary code
    (e.g., executing system commands, file writes, importing libraries, or running page.evaluate)
    is caught and rejected by the validator, causing code generation to fail.
    """
    spec = _load_spec_from_session(FIXTURE_SINGLE, [
        {"name": "search_input", "example_value": "hello", "log_step_index": 1, "is_sensitive": False}
    ], [0, 2], "Search workflow")

    adversarial_payloads = [
        "import os\nos.system('rm -rf /')",
        "__import__('subprocess').run(['echo', 'hacked'])",
        "eval('page.goto(url)')",
        "open('/etc/passwd', 'r').read()",
        "await page.evaluate('() => alert(1)')",
    ]

    for payload in adversarial_payloads:
        def mock_llm_return(messages, *args, **kwargs):
            return payload

        with patch(
            "browserbot.agents.code_generator.generator._call_llm",
            side_effect=mock_llm_return,
        ):
            # Limit retries to 0 so it fails immediately upon validation rejection
            generator = CodeGenerator(dry_run=False, backend="ollama", max_retries=0)
            with pytest.raises(RuntimeError) as exc_info:
                generator.generate(spec)

            assert "Code generation failed after 1 attempt(s)" in str(exc_info.value)

