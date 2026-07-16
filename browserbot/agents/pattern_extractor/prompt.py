"""
browserbot/agents/pattern_extractor/prompt.py — Step 3.1: Prompt design.

PHILOSOPHY
----------
The prompt is intentionally narrow in scope. The LLM is asked to do ONE
thing: distinguish dynamic values from fixed values in a browser action log.

It is NOT asked to:
  - reason about Playwright
  - generate any code
  - describe what it is doing
  - provide explanations or commentary
  - produce markdown

This narrowness is a reliability decision, not a limitation. Smaller local
open-weight models (llama3.1:8b, qwen2.5-coder) are demonstrably more
reliable when their task is precisely constrained. The output schema
(validated on the response side) is what enforces this, but the prompt
must also make the constraint explicit.

OUTPUT CONTRACT
---------------
The model must output a single, valid JSON object matching this schema:

    {
      "parameters": [
        {
          "name": "order_id",
          "example_value": "NBC-2026-8F3K2Q",
          "log_step_index": 2,
          "description": "The order code to track"
        }
      ],
      "fixed_step_indices": [0, 1, 3, 4, 5, 6],
      "workflow_description": "Checks the tracking status of an order"
    }

If there are no dynamic parameters, return:

    {
      "parameters": [],
      "fixed_step_indices": [0, 1, 2, ...],
      "workflow_description": "..."
    }

WHY INCLUDE fixed_step_indices EXPLICITLY
------------------------------------------
Without this field, Phase 4's Code Generator would have to recompute which
steps are parameterised vs fixed by comparing step indices against parameter
log_step_index values. That is error-prone (off-by-one risks, out-of-range
indices). Asking the LLM to enumerate fixed_step_indices explicitly also
forces it to consider every step in the log — reducing the chance it silently
skips a step that should have been parameterised.

DETERMINISM
-----------
The system prompt includes the JSON schema inline so the model sees the
exact format it must produce. The temperature will be set to 0 by the caller
to reduce variation. The prompt avoids open-ended questions.
"""

from __future__ import annotations

import json
from pathlib import Path

# Inline schema for injection into prompts — keeps the prompt self-contained
_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "docs" / "schemas" / "extractor_output_schema.json"
)


def _load_output_schema_excerpt() -> str:
    """Return a concise representation of the output schema for the prompt."""
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)

    # Extract only the parts the model needs to see (not the full $defs JSON)
    excerpt = {
        "required": schema.get("required", []),
        "properties": {
            "parameters": {
                "type": "array",
                "items": {
                    "required": ["name", "example_value", "log_step_index"],
                    "properties": {
                        "name": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
                        "example_value": {"type": "string"},
                        "log_step_index": {"type": "integer", "minimum": 0},
                        "description": {"type": "string"},
                        "is_sensitive": {"type": "boolean"},
                    },
                },
            },
            "fixed_step_indices": {
                "type": "array",
                "items": {"type": "integer", "minimum": 0},
            },
            "workflow_description": {"type": "string"},
        },
    }
    return json.dumps(excerpt, indent=2)


SYSTEM_PROMPT: str = """\
You are a browser workflow analyser. Your only job is to read a browser action log \
and identify which input fields contain dynamic user-supplied values (parameters) \
versus fixed structural steps.

RULES:
1. Output ONLY a single JSON object. No markdown. No explanation. No prose.
2. The JSON must exactly match the schema below.
3. A "parameter" is any fill step whose value would change between workflow runs \
(e.g. an order ID, a search query, a username that varies per user).
4. Navigation steps (goto), clicks, waits, and text extractions are ALWAYS fixed steps.
5. Fill steps whose value never changes between runs are fixed steps.
6. If there are no parameters, output an empty parameters array.
7. Include every step_index in either a parameter's log_step_index or in fixed_step_indices.
8. Do not invent step indices that are not in the log.
9. The workflow_description must be one sentence describing what the workflow does \
for an end user. Do not mention Playwright, BrowserBot, or automation.
10. The parameter "name" MUST be strictly in lowercase snake_case format (e.g. "order_id", "zip_code", "username"). \
No spaces, no uppercase characters, and it must start with a letter.

OUTPUT SCHEMA:
{output_schema}

EXAMPLE (for a login workflow):
{{"parameters":[{{"name":"username","example_value":"alice@example.com","log_step_index":1,"description":"User email address","is_sensitive":false}},{{"name":"password","example_value":"__SECRET_1__","log_step_index":2,"description":"User password","is_sensitive":true}}],"fixed_step_indices":[0,3,4],"workflow_description":"Logs into the application with a given username and password."}}
"""

USER_PROMPT_TEMPLATE: str = """\
Analyse the following browser action log and extract parameters.

SITE: {site}
WORKFLOW HINT: {workflow_hint}

ACTION LOG:
{action_log_json}

Output only the JSON object. No other text.
"""


def build_system_prompt() -> str:
    """
    Build the system prompt with the output schema injected inline.

    The schema excerpt is injected at build time (not at call time) so the
    prompt is stable and cacheable.
    """
    return SYSTEM_PROMPT.format(output_schema=_load_output_schema_excerpt())


def build_user_prompt(
    *,
    action_log_json: str,
    site: str,
    workflow_hint: str | None,
) -> str:
    """
    Build the user-turn prompt for a specific action log.

    Args:
        action_log_json:  The serialised ActionLog (JSON string).
        site:             The hostname from the session metadata.
        workflow_hint:    Optional user-provided hint about the workflow's purpose.

    Returns:
        The formatted user prompt string.
    """
    return USER_PROMPT_TEMPLATE.format(
        site=site or "(unknown)",
        workflow_hint=workflow_hint or "(none provided)",
        action_log_json=action_log_json,
    )
