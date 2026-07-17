"""
browserbot/agents/code_generator/prompt.py — Step 4.2: Code Generator prompts.

Defines the system and user prompts instructing the code-specialized model
to output ONLY raw Python statement lines containing safe Playwright actions
from the approved DSL.
"""

from __future__ import annotations

SYSTEM_PROMPT: str = """\
You are an expert browser automation generator. Your only job is to read a \
parameterized workflow specification (Intermediate Representation) and translate \
its steps into a sequence of executable Python Playwright statements.

RULES:
1. Output ONLY raw Python code lines.
2. Do NOT output markdown code fences (e.g. do not wrap in ```python ... ```).
3. Do NOT output any explanations, commentary, or introduction/outro text.
4. Do NOT output imports, function definitions, or async def wraps. The code you write \
   will be directly inserted into an async function body that has a `page` variable already in scope.
5. Reference parameters by their literal parameter variable name (e.g. if the parameter name is `order_id`, use `order_id` in the code, do not hardcode the example value).
6. Restrict generation strictly to the approved DSL below.
7. Use the `resolve_locator(page, selector_dict)` function for clicks, fills, and waits. Pass the full selector details dictionary parameter to resolve_locator.

APPROVED PLAYWRIGHT DSL:
- page.goto(url)
- resolve_locator(page, selector_dict)  (returns a locator by resolving multiple prioritized fallbacks)
- locator.fill(value)  (where value can be a variable or string)
- locator.click()
- locator.press(key)
- page.wait_for_timeout(ms)
- locator.text_content() or locator.inner_text()
- Locator filters (if resolved locator needs sub-filtering):
  - locator.first
  - locator.nth(index)

REJECTED OPERATIONS (These will fail static analysis):
- imports (import os, sys, etc.)
- file system / network calls (open, urllib, socket)
- exec, eval, subprocess, print, or arbitrary Python commands
- loops, class definitions, function definitions

EXAMPLE:
Given the following steps:
1. goto "https://example.com"
2. fill element with selector {"value": "Search", "strategy": "label"} with parameter "search_term"
3. click element with selector {"value": "button:Search", "strategy": "role", "aria_role": "button", "aria_name": "Search"}

Output:
await page.goto("https://example.com")
await (await resolve_locator(page, {"value": "Search", "strategy": "label"})).fill(search_term)
await (await resolve_locator(page, {"value": "button:Search", "strategy": "role", "aria_role": "button", "aria_name": "Search"})).click()
"""

from browserbot.models.correction_payload import CorrectionPayload

USER_PROMPT_TEMPLATE: str = """\
Translate the following workflow spec steps into Python Playwright statements.

WORKFLOW SPEC:
{workflow_spec_json}

Output only the Python statements. No markdown. No comments.
"""


def build_system_prompt() -> str:
    """Return the system prompt for the Code Generator agent."""
    return SYSTEM_PROMPT


def build_user_prompt(
    *,
    workflow_spec_json: str,
    correction: CorrectionPayload | None = None,
) -> str:
    """
    Build the user prompt for a specific workflow spec, optionally including error feedback context.

    Args:
        workflow_spec_json: The serialised WorkflowSpec (JSON string).
        correction: Optional CorrectionPayload representing a prior failure.

    Returns:
        The formatted user prompt.
    """
    prompt = USER_PROMPT_TEMPLATE.format(workflow_spec_json=workflow_spec_json)
    
    if correction:
        snippet_part = ""
        if correction.relevant_code_snippet:
            snippet_part = f"\nRelevant generated code that caused the text/layout issue:\n{correction.relevant_code_snippet}\n"

        feedback = (
            f"\n\nPREVIOUS GENERATION ERROR:\n"
            f"The previous generated code failed validation. Here is the feedback to help you correct the issue:\n"
            f"- Validation Stage: {correction.validation_stage}\n"
            f"- Error Category: {correction.error_category}\n"
            f"- Validation Summary: {correction.validation_summary}\n"
            f"- Exception details: {correction.exception}\n"
            f"{snippet_part}\n"
            f"Please correct this issue in your output code. Ensure the final code is complete and solves the error."
        )
        prompt += feedback

    return prompt
