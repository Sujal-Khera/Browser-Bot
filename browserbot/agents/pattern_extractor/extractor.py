"""
browserbot/agents/pattern_extractor/extractor.py — Step 3.1: Pattern Extractor.

RESPONSIBILITY
--------------
This module implements BrowserBot's first LLM agent.

Given an ActionLog, it:
  1. Builds a prompt (system + user) from the action log JSON.
  2. Calls the configured LLM backend via LiteLLM.
  3. Parses the response as JSON.
  4. Validates the parsed JSON against the extractor output schema.
  5. Retries (up to max_retries) on malformed or invalid JSON.
  6. Returns a validated ExtractorOutput.

ISOLATION
---------
This module is completely isolated from Phase 4 (Code Generator) and beyond.
It does NOT:
  - Generate any code
  - Write any files to disk
  - Know about Playwright, FastMCP, or the Validator
  - Interact with the filesystem beyond reading the action log

DRY-RUN MODE
------------
In dry-run mode, the LLM is NOT called.  Instead, a deterministic stub
response is returned, derived from the action log itself by inspecting
fill steps.  This enables offline development and testing without Ollama.

BACKEND SELECTION
-----------------
Backend selection is entirely configuration-driven (settings.llm_backend).

LiteLLM model identifiers:
  - Ollama: "ollama/<model_name>"  (e.g. "ollama/llama3.1:8b")
  - Groq:   "groq/<model_name>"    (e.g. "groq/llama-3.3-70b-versatile")

The LiteLLM abstraction makes the caller completely backend-agnostic.
Switching from Ollama to Groq is a config change, not a code change.

RETRY STRATEGY
--------------
Local open-weight models (especially smaller ones like llama3.1:8b) may
occasionally output trailing text, markdown fences, or malformed JSON.

The retry loop:
  1. Sends the full conversation to the model.
  2. Attempts to extract and parse JSON from the response.
  3. If parsing or schema validation fails, appends a correction message
     to the conversation and retries.
  4. Gives up after max_retries attempts and raises ExtractionError.

This "correction injection" approach is more effective than a cold restart
because the model sees its own bad output and the specific error alongside
the correction instruction.

TEMPERATURE
-----------
Temperature is set to 0.0 for maximum determinism.  The task is not
creative — it is structural analysis. Lower temperature = less drift.
"""

from __future__ import annotations

import json
import re
from typing import Any

import litellm

from browserbot.agents.pattern_extractor.models import (
    ExtractorOutput,
    ExtractorOutputValidator,
)
from browserbot.agents.pattern_extractor.prompt import build_system_prompt, build_user_prompt
from browserbot.config.settings import settings
from browserbot.logging import get_logger
from browserbot.models.action_log import ActionLog, FillStep

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ExtractionError(RuntimeError):
    """
    Raised when the Pattern Extractor fails to produce a valid output after
    all retries have been exhausted.

    Attributes:
        attempts:      Number of LLM calls made before giving up.
        last_response: Raw text of the last LLM response (for diagnostics).
        errors:        Schema validation errors from the last attempt.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        last_response: str = "",
        errors: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_response = last_response
        self.errors = errors or []


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    """
    Attempt to extract a JSON object from a (possibly messy) LLM response.

    Strategy:
      1. Try to parse the entire text as JSON (best case).
      2. Find the first '{' and last '}' and try to parse the substring.
      3. Strip common markdown fences (```json ... ```) and retry.

    Returns None if no valid JSON object can be extracted.
    """
    text = text.strip()

    # 1. Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown fences
    stripped = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # 3. Find first { ... last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


# ---------------------------------------------------------------------------
# Dry-run stub
# ---------------------------------------------------------------------------


def _build_dry_run_output(action_log: ActionLog) -> ExtractorOutput:
    """
    Build a deterministic ExtractorOutput without calling the LLM.

    Used in dry-run mode and in tests.  Classifies every fill step as a
    parameter and everything else as a fixed step.  This is intentionally
    conservative — a human (Step 3.2) will reject false positives.
    """
    from browserbot.agents.pattern_extractor.models import ExtractedParameter

    parameters = []
    fixed_step_indices = []

    for step in action_log.steps:
        if isinstance(step, FillStep):
            snake_name = re.sub(r"[^a-z0-9]+", "_", step.selector.value.lower()).strip("_")
            if not snake_name or not snake_name[0].isalpha():
                snake_name = f"param_{step.step_index}"
            parameters.append(
                ExtractedParameter(
                    name=snake_name[:40],
                    example_value=step.value,
                    log_step_index=step.step_index,
                    description=f"Value entered in field '{step.selector.value}'",
                    is_sensitive=step.is_sensitive,
                )
            )
        else:
            fixed_step_indices.append(step.step_index)

    hint = action_log.metadata.workflow_hint or ""
    return ExtractorOutput(
        parameters=parameters,
        fixed_step_indices=sorted(fixed_step_indices),
        workflow_description=hint or f"Automates a workflow on {action_log.metadata.site}",
    )


# ---------------------------------------------------------------------------
# LiteLLM model name builder
# ---------------------------------------------------------------------------


def _resolve_model_name(backend: str | None = None) -> str:
    """
    Resolve the LiteLLM model identifier for the Pattern Extractor.

    LiteLLM expects:
      - "ollama/<model>"  for Ollama
      - "groq/<model>"    for Groq

    Args:
        backend: Override backend name (for testing). Defaults to settings.

    Returns:
        A LiteLLM-compatible model string.
    """
    active_backend = (backend or settings.llm_backend).lower()

    if active_backend == "ollama":
        model = settings.ollama_model_extractor
        return f"ollama/{model}"
    elif active_backend == "groq":
        model = settings.groq_model
        return f"groq/{model}"
    else:
        raise ValueError(
            f"Unknown LLM backend: {active_backend!r}. "
            "Set BROWSERBOT_LLM_BACKEND to 'ollama' or 'groq'."
        )


# ---------------------------------------------------------------------------
# LiteLLM call helper
# ---------------------------------------------------------------------------


def _call_llm(
    messages: list[dict[str, str]],
    *,
    model: str,
    temperature: float = 0.0,
) -> str:
    """
    Call the LLM via LiteLLM and return the assistant's text response.

    Args:
        messages:    Conversation history (list of role/content dicts).
        model:       LiteLLM model string (e.g. "ollama/llama3.1:8b").
        temperature: Sampling temperature.

    Returns:
        The assistant's response text (stripped).

    Raises:
        ExtractionError: If the LLM API call fails.
    """
    try:
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
        )
        content = response.choices[0].message.content or ""
        return content.strip()
    except Exception as exc:
        raise ExtractionError(
            f"LLM call failed: {exc}",
            last_response="",
        ) from exc


# ---------------------------------------------------------------------------
# Main extractor class
# ---------------------------------------------------------------------------


class PatternExtractor:
    """
    Phase 3 LLM agent: identifies dynamic parameters in an ActionLog.

    Usage::

        extractor = PatternExtractor()
        output = extractor.extract(action_log)
        # output.parameters  — list of ExtractedParameter
        # output.fixed_step_indices  — list of int

    Dry-run mode::

        extractor = PatternExtractor(dry_run=True)
        output = extractor.extract(action_log)  # no LLM call

    Args:
        dry_run:     If True, skip the LLM call and return a stub output.
        backend:     Override the LLM backend ("ollama" | "groq"). Defaults
                     to settings.llm_backend.
        max_retries: Maximum number of LLM retries on malformed output.
        temperature: LLM sampling temperature. 0.0 = fully deterministic.
    """

    def __init__(
        self,
        *,
        dry_run: bool = False,
        backend: str | None = None,
        max_retries: int | None = None,
        temperature: float = 0.0,
    ) -> None:
        self._dry_run = dry_run
        self._model = _resolve_model_name(backend) if not dry_run else "(dry-run)"
        self._max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        self._temperature = temperature
        self._validator = ExtractorOutputValidator()
        # Only build the system prompt when we will actually call the LLM
        self._system_prompt = "" if dry_run else build_system_prompt()

        log.info(
            "PatternExtractor initialised",
            extra={
                "model": self._model,
                "dry_run": self._dry_run,
                "max_retries": self._max_retries,
                "temperature": self._temperature,
            },
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, action_log: ActionLog) -> ExtractorOutput:
        """
        Extract parameters from an ActionLog.

        Args:
            action_log: A validated ActionLog (from Phase 2).

        Returns:
            A validated :class:`ExtractorOutput`.

        Raises:
            ExtractionError: If LLM fails to produce valid output after retries.
        """
        log.info(
            "Pattern extraction started",
            extra={
                "session_id": action_log.metadata.session_id,
                "steps": len(action_log.steps),
                "dry_run": self._dry_run,
            },
        )

        if self._dry_run:
            output = _build_dry_run_output(action_log)
            log.info(
                "Pattern extraction complete (dry-run)",
                extra={
                    "session_id": action_log.metadata.session_id,
                    "parameters": len(output.parameters),
                },
            )
            return output

        return self._extract_with_llm(action_log)

    # ------------------------------------------------------------------
    # Internal — LLM extraction with retry loop
    # ------------------------------------------------------------------

    def _extract_with_llm(self, action_log: ActionLog) -> ExtractorOutput:
        """
        Call the LLM with a retry loop for malformed output.

        The retry strategy appends a correction message to the conversation
        showing the model what went wrong, then asks it to try again.
        """
        action_log_json = json.dumps(
            action_log.model_dump(mode="json", exclude_none=True),
            indent=2,
        )

        user_prompt = build_user_prompt(
            action_log_json=action_log_json,
            site=action_log.metadata.site,
            workflow_hint=action_log.metadata.workflow_hint,
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_response = ""
        last_errors: list[str] = []

        for attempt in range(1, self._max_retries + 2):  # +1 for initial attempt
            log.info(
                "LLM call attempt",
                extra={
                    "attempt": attempt,
                    "max": self._max_retries + 1,
                    "model": self._model,
                    "session_id": action_log.metadata.session_id,
                },
            )

            try:
                raw_response = _call_llm(
                    messages,
                    model=self._model,
                    temperature=self._temperature,
                )
            except ExtractionError as exc:
                log.error(
                    "LLM API call failed",
                    extra={
                        "attempt": attempt,
                        "error": str(exc),
                        "session_id": action_log.metadata.session_id,
                    },
                )
                raise

            last_response = raw_response
            log.debug(
                "LLM raw response received",
                extra={"attempt": attempt, "length": len(raw_response)},
            )

            # Step 1: Try to extract JSON from possibly messy response
            parsed = _extract_json_from_text(raw_response)
            if parsed is None:
                last_errors = ["Response does not contain a valid JSON object"]
                log.warning(
                    "LLM response is not valid JSON",
                    extra={"attempt": attempt, "response_preview": raw_response[:200]},
                )
                if attempt <= self._max_retries:
                    messages = self._inject_correction(
                        messages, raw_response, ["Response must be a valid JSON object"]
                    )
                continue

            # Step 2: Validate parsed JSON against the output schema
            validation_errors = self._validator.validate(parsed)
            if validation_errors:
                last_errors = validation_errors
                log.warning(
                    "LLM output failed schema validation",
                    extra={
                        "attempt": attempt,
                        "errors": validation_errors,
                    },
                )
                if attempt <= self._max_retries:
                    messages = self._inject_correction(
                        messages, raw_response, validation_errors
                    )
                continue

            # Step 3: Parse into ExtractorOutput
            try:
                output = ExtractorOutput.model_validate(parsed)
            except Exception as exc:
                last_errors = [str(exc)]
                log.warning(
                    "ExtractorOutput model validation failed",
                    extra={"attempt": attempt, "error": str(exc)},
                )
                if attempt <= self._max_retries:
                    messages = self._inject_correction(messages, raw_response, [str(exc)])
                continue

            # Success
            log.info(
                "Pattern extraction complete",
                extra={
                    "session_id": action_log.metadata.session_id,
                    "attempt": attempt,
                    "parameters": len(output.parameters),
                    "fixed_steps": len(output.fixed_step_indices),
                },
            )
            return output

        # All attempts exhausted
        raise ExtractionError(
            f"Pattern extraction failed after {self._max_retries + 1} attempt(s). "
            f"The LLM did not produce valid JSON output matching the required schema.",
            attempts=self._max_retries + 1,
            last_response=last_response,
            errors=last_errors,
        )

    def _inject_correction(
        self,
        messages: list[dict[str, str]],
        bad_response: str,
        errors: list[str],
    ) -> list[dict[str, str]]:
        """
        Append the model's bad response and a correction instruction to
        the conversation before the next retry.

        This is more effective than a cold restart because the model sees
        both its mistake and the specific error.
        """
        error_text = "\n".join(f"  - {e}" for e in errors)
        correction = (
            f"Your previous response was invalid:\n{bad_response[:500]}\n\n"
            f"Errors:\n{error_text}\n\n"
            "Output ONLY a single valid JSON object matching the required schema. "
            "No markdown. No explanation."
        )
        return messages + [
            {"role": "assistant", "content": bad_response},
            {"role": "user", "content": correction},
        ]
