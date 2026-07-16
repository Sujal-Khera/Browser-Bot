"""
browserbot/recorder/scrubber.py — Step 2.4: PII / Secret scrubbing.

PURPOSE
-------
This module implements the security boundary for BrowserBot recordings.

Every ActionLog passes through this scrubber before being written to disk.
No plaintext sensitive value ever reaches a session JSON file.

DESIGN
------
The scrubber operates on an ActionLog (a Pydantic model) produced by the
converter. It walks every FillStep, detects whether it is sensitive, and
produces a NEW ActionLog with the sensitive values replaced by stable
placeholders (`__SECRET_1__`, `__SECRET_2__`, etc.).

The original ActionLog argument is NEVER modified (pure function semantics).
Callers must use ``ScrubResult.action_log`` to obtain the scrubbed version.

It does NOT:
  - modify any other step type (click, goto, extract_text, etc.)
  - delete sensitive steps — the action itself is preserved for replay
  - interact with any LLM
  - perform cryptographic hashing of values
  - access the filesystem

SENSITIVE DETECTION
-------------------
A FillStep is flagged as sensitive if ANY of the following are true:

  1. The selector value contains a sensitive keyword (case-insensitive).
     Matches field names like `password`, `passwd`, `token`, etc.

  2. The field_label (if present) contains a sensitive keyword.
     Matches visible labels like "Password", "API Key", "Auth Token".

  3. The selector value is present in the configurable extra selector set.
     Populated from BROWSERBOT_SENSITIVE_SELECTORS env var (comma-separated)
     or passed directly to the scrubber for programmatic use.

PLACEHOLDER STRATEGY
--------------------
Placeholders are assigned in the order they are encountered:

    First sensitive field  →  __SECRET_1__
    Second sensitive field →  __SECRET_2__
    ...

If the SAME plaintext value appears more than once (e.g. a password
re-confirmation field), it maps to the SAME placeholder — the mapping is
value → placeholder, not step → placeholder.

This means:
  - Identical values across the recording share one stable placeholder ID.
  - Different values get different IDs.
  - The counter is session-scoped (starts at 1 for every session).

WHY REPLACE INSTEAD OF REMOVE
-------------------------------
Removing the step would break:
  1. The Validator (Phase 5): replay would skip the input field, causing the
     form to submit without required data → test failure.
  2. The Code Generator (Phase 4): generated code would be missing the fill
     step entirely → the generated tool would not work.
  3. step_index ordering: removing a step would create gaps and break the
     schema's step_index invariant.

Replacing with a placeholder preserves the action's position and structure
while ensuring the plaintext value is never stored.  When a generated tool
runs live, it will receive the real value from the MCP tool's input parameters.

EXTENSION POINTS
----------------
  - Additional keyword categories (e.g. credit card, SSN) can be added to
    `DEFAULT_SENSITIVE_KEYWORDS` without touching any call sites.
  - Per-site override lists can be passed as `extra_selectors` to `Scrubber`.
  - The `ScrubResult` dataclass carries full provenance: which steps were
    scrubbed, what values were replaced, and how many secrets were assigned.

CONFIGURATION
-------------
  BROWSERBOT_SENSITIVE_SELECTORS — comma-separated list of CSS selectors or
      field labels to treat as always sensitive, regardless of keyword matching.
      Example: "input#api_key,input[name=token],My Custom Field"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from browserbot.logging import get_logger
from browserbot.models.action_log import ActionLog, FillStep

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Default sensitive keyword list
# ---------------------------------------------------------------------------

DEFAULT_SENSITIVE_KEYWORDS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "pass",
        "secret",
        "token",
        "credential",
        "credentials",
        "auth",
        "apikey",
        "api_key",
        "api-key",
        "accesskey",
        "access_key",
        "access-key",
        "privatekey",
        "private_key",
        "private-key",
        "otp",
        "pin",
        "ssn",
        "cvv",
        "cvc",
        "passphrase",
    }
)

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ScrubResult:
    """
    Summary of what the scrubber did to an ActionLog.

    Attributes:
        scrubbed_count:    Total number of FillStep values replaced.
        secret_count:      Number of distinct secret values encountered.
        step_indices:      Indices of every step that was modified.
        value_map:         Mapping of plaintext value → placeholder.
                           This is kept in memory ONLY — never serialised.
        action_log:        The new scrubbed ActionLog (distinct object from
                           the input; use this, not the original).
    """

    scrubbed_count: int = 0
    secret_count: int = 0
    step_indices: list[int] = field(default_factory=list)
    value_map: dict[str, str] = field(default_factory=dict)   # NOT logged or persisted
    action_log: ActionLog | None = None


# ---------------------------------------------------------------------------
# Scrubber class
# ---------------------------------------------------------------------------


class Scrubber:
    """
    Walks an ActionLog and replaces sensitive FillStep values with placeholders.

    Pure function semantics: the input ActionLog is never modified.
    The scrubbed copy is returned in ``ScrubResult.action_log``.

    Args:
        sensitive_keywords:  Set of lowercase keywords used for detection.
                             Defaults to :data:`DEFAULT_SENSITIVE_KEYWORDS`.
        extra_selectors:     Additional selector values / label strings that
                             always trigger redaction regardless of keywords.
                             Loaded from ``BROWSERBOT_SENSITIVE_SELECTORS``
                             env var if not supplied explicitly.
    """

    def __init__(
        self,
        *,
        sensitive_keywords: frozenset[str] | None = None,
        extra_selectors: set[str] | None = None,
    ) -> None:
        self._keywords: frozenset[str] = sensitive_keywords or DEFAULT_SENSITIVE_KEYWORDS

        if extra_selectors is not None:
            self._extra: set[str] = {s.strip().lower() for s in extra_selectors if s.strip()}
        else:
            env_val = os.getenv("BROWSERBOT_SENSITIVE_SELECTORS", "")
            self._extra = {s.strip().lower() for s in env_val.split(",") if s.strip()}

        log.debug(
            "Scrubber initialised",
            extra={
                "keywords": len(self._keywords),
                "extra_selectors": len(self._extra),
            },
        )

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def _is_sensitive(self, step: FillStep) -> bool:
        """
        Return True if this FillStep should have its value redacted.

        Detection order:
          1. selector.value keyword match
          2. field_label keyword match
          3. extra_selectors set membership
        """
        sel_lower = step.selector.value.lower()

        # 1. Keyword match in selector value
        for kw in self._keywords:
            if kw in sel_lower:
                log.debug(
                    "Sensitive field detected (selector keyword)",
                    extra={"selector": step.selector.value, "keyword": kw},
                )
                return True

        # 2. Keyword match in visible label
        if step.field_label:
            label_lower = step.field_label.lower()
            for kw in self._keywords:
                if kw in label_lower:
                    log.debug(
                        "Sensitive field detected (label keyword)",
                        extra={"label": step.field_label, "keyword": kw},
                    )
                    return True

        # 3. Extra selectors set
        if sel_lower in self._extra or (
            step.field_label and step.field_label.lower() in self._extra
        ):
            log.debug(
                "Sensitive field detected (extra_selectors)",
                extra={"selector": step.selector.value},
            )
            return True

        return False

    # ------------------------------------------------------------------
    # Scrubbing
    # ------------------------------------------------------------------

    def scrub(self, action_log: ActionLog) -> ScrubResult:
        """
        Scrub sensitive values from every FillStep in the ActionLog.

        Produces a NEW ActionLog (via ``model_copy``) with sensitive values
        replaced by placeholders.  The original ``action_log`` argument is
        **never modified** (pure function semantics).

        Args:
            action_log: The ActionLog to scrub.

        Returns:
            A :class:`ScrubResult` where ``.action_log`` is the scrubbed copy
            and ``.scrubbed_count`` is the number of steps that were changed.
        """
        result = ScrubResult()
        value_to_placeholder: dict[str, str] = {}  # NOT logged or persisted
        counter = 0

        scrubbed_steps: list[Any] = list(action_log.steps)

        for i, step in enumerate(action_log.steps):
            if not isinstance(step, FillStep):
                continue
            if not self._is_sensitive(step):
                continue

            plaintext = step.value

            # Reuse the same placeholder if this exact value was seen before
            if plaintext in value_to_placeholder:
                placeholder = value_to_placeholder[plaintext]
                log.debug(
                    "Reusing existing placeholder for repeated value",
                    extra={"step_index": step.step_index, "placeholder": placeholder},
                )
            else:
                counter += 1
                placeholder = f"__SECRET_{counter}__"
                value_to_placeholder[plaintext] = placeholder
                result.secret_count += 1
                log.info(
                    "Sensitive value redacted",
                    extra={
                        "step_index": step.step_index,
                        "selector": step.selector.value,
                        "placeholder": placeholder,
                    },
                )

            # Produce a scrubbed copy of the step (Pydantic model_copy is safe)
            scrubbed_step = step.model_copy(
                update={"value": placeholder, "is_sensitive": True}
            )
            scrubbed_steps[i] = scrubbed_step
            result.scrubbed_count += 1
            result.step_indices.append(step.step_index)

        # Produce a new ActionLog with the scrubbed steps.
        # model_copy does NOT re-run __init__ validators (ordering, step_count
        # checks etc.), which is correct — we are only changing FillStep values,
        # not reordering steps.
        scrubbed_log = action_log.model_copy(update={"steps": scrubbed_steps})

        result.value_map = value_to_placeholder
        result.action_log = scrubbed_log
        log.info(
            "Scrub complete",
            extra={
                "scrubbed_count": result.scrubbed_count,
                "secret_count": result.secret_count,
                "step_indices": result.step_indices,
            },
        )
        return result


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


def scrub(
    action_log: ActionLog,
    *,
    extra_selectors: set[str] | None = None,
) -> ScrubResult:
    """
    Scrub an ActionLog using default configuration.

    This is the primary entry point for the codegen runner pipeline::

        action_log = convert_codegen_script(...)
        result = scrub(action_log)
        result.action_log.to_file(path)   # use result.action_log, not action_log

    Args:
        action_log:      The ActionLog to scrub.
        extra_selectors: Optional additional selectors to treat as sensitive.

    Returns:
        :class:`ScrubResult` where ``.action_log`` is the scrubbed copy.
    """
    return Scrubber(extra_selectors=extra_selectors).scrub(action_log)
