"""
tests/test_converter.py — Automated tests for convert_codegen.py script converter.
"""

from __future__ import annotations

from browserbot.recorder.convert_codegen import (
    convert_codegen_script,
    _extract_string_literal,
    _extract_locator_value,
    _infer_strategy,
)


def test_extract_string_literal() -> None:
    # Double quoted basic
    assert _extract_string_literal("locator", 'locator("username")') == "username"
    # Single quoted basic
    assert _extract_string_literal("locator", "locator('username')") == "username"

    # Escaped double quotes
    assert _extract_string_literal("locator", 'locator("[data-test=\\"username\\"]")') == '[data-test="username"]'
    # Escaped single quotes
    assert _extract_string_literal("locator", "locator('[data-test=\\'username\\']')") == "[data-test='username']"

    # Keyword double quoted name
    assert _extract_string_literal("name", 'get_by_role("button", name="Submit")') == "Submit"
    # Keyword single quoted name
    assert _extract_string_literal("name", "get_by_role('button', name='Submit')") == "Submit"
    # Keyword double quoted name with spaces
    assert _extract_string_literal("name", 'get_by_role("button", name = "Submit Work")') == "Submit Work"


def test_extract_locator_value_and_strategy() -> None:
    # Plain locator
    assert _extract_locator_value('locator("username")') == "username"
    strategy, _ = _infer_strategy('locator("username")')
    assert strategy == "css"

    # Escaped locator selector
    assert _extract_locator_value('locator("[data-test=\\"username\\"]")') == '[data-test="username"]'

    # get_by_label
    assert _extract_locator_value('get_by_label("First Name")') == "First Name"
    strategy, _ = _infer_strategy('get_by_label("First Name")')
    assert strategy == "label"

    # get_by_role
    assert _extract_locator_value('get_by_role("button", name="Submit")') == "button:Submit"
    strategy, extras = _infer_strategy('get_by_role("button", name="Submit")')
    assert strategy == "role"
    assert extras["aria_role"] == "button"
    assert extras["aria_name"] == "Submit"


def test_convert_codegen_script_success() -> None:
    script = """
import re
from playwright.sync_api import Playwright, sync_playwright, expect

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto("https://www.saucedemo.com/")
    page.locator("[data-test=\\"username\\"]").click()
    page.locator("[data-test=\\"username\\"]").fill("standard_user")
    page.locator("[data-test=\\"password\\"]").fill("secret_sauce")
    page.locator("[data-test=\\"login-button\\"]").click()
    context.close()
    browser.close()
"""
    log = convert_codegen_script(script, site="saucedemo.com")
    assert len(log.steps) == 5
    assert log.steps[0].action == "goto"
    assert log.steps[1].action == "click"
    assert log.steps[1].selector.value == '[data-test="username"]'
    assert log.steps[2].action == "fill"
    assert log.steps[2].value == "standard_user"
    assert log.steps[3].value == "secret_sauce"
    assert log.steps[4].action == "click"
    assert log.steps[4].selector.value == '[data-test="login-button"]'
