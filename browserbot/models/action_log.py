"""
browserbot/models/action_log.py — Step 2.1: Action Log data models and schema validator.

This module defines:

1. Pydantic data models for every Action Log action type.
   These are the Python-native contracts for the JSON schema defined in
   docs/schemas/action_log_schema.json.

2. A schema validator (ActionLogValidator) that validates a raw JSON dict
   against the JSON Schema.  This is the gating check run by:
     - the Recorder before writing a session to disk (Phase 2)
     - the Pattern Extractor before consuming a log (Phase 3)
     - unit tests to guard schema stability

DESIGN NOTES
------------
- The JSON Schema (docs/schemas/action_log_schema.json) is the authoritative
  contract.  These Pydantic models mirror it for Python-land type safety.
- When the two diverge, the JSON Schema wins.
- Models are intentionally strict: no extra fields allowed, all required fields
  typed precisely.  This prevents silent data drift between phases.
- The schema version is a Literal["1.0"] so version mismatches are caught at
  parse time, not at runtime inside a downstream agent.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any, Literal, Union

import jsonschema
from pydantic import BaseModel, Field, model_validator

from browserbot.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Path to the JSON Schema file (single source of truth)
# ---------------------------------------------------------------------------

SCHEMA_PATH: Path = (
    Path(__file__).resolve().parents[2] / "docs" / "schemas" / "action_log_schema.json"
)


# ---------------------------------------------------------------------------
# Selector model (shared across action types)
# ---------------------------------------------------------------------------


class SelectorInfo(BaseModel):
    """Locator used to find the target element on the page."""

    model_config = {"extra": "forbid"}

    value: str = Field(description="Selector string as passed to Playwright.")
    strategy: Literal[
        "css", "xpath", "text", "role", "label", "placeholder", "test_id", "nth", "other"
    ] = Field(default="css", description="Selector strategy used.")
    aria_role: str | None = Field(
        default=None,
        description="ARIA role filter when strategy='role'.",
    )
    aria_name: str | None = Field(
        default=None,
        description="Accessible name filter when strategy='role'.",
    )


# ---------------------------------------------------------------------------
# Base step (fields common to every action)
# ---------------------------------------------------------------------------


class BaseStep(BaseModel):
    """Fields present on every step."""

    model_config = {"extra": "forbid"}

    step_index: int = Field(ge=0)
    action: str
    timestamp_offset: float = Field(ge=0.0)
    frame_url: str | None = None
    page_title: str | None = None


# ---------------------------------------------------------------------------
# Concrete step types — one per action discriminator value
# ---------------------------------------------------------------------------


class GotoStep(BaseStep):
    action: Literal["goto"] = "goto"
    url: str
    wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load"


class FillStep(BaseStep):
    action: Literal["fill"] = "fill"
    selector: SelectorInfo
    value: str
    is_sensitive: bool = False
    field_label: str | None = None

    @model_validator(mode="after")
    def sensitive_fields_must_be_scrubbed(self) -> "FillStep":
        """Enforce the PII scrubbing contract from Step 2.4."""
        if self.is_sensitive and not self.value.startswith("__SECRET_"):
            raise ValueError(
                f"FillStep with is_sensitive=True must have a scrubbed value "
                f"(starting with '__SECRET_'), got: {self.value!r}"
            )
        return self


class ClickStep(BaseStep):
    action: Literal["click"] = "click"
    selector: SelectorInfo
    button: Literal["left", "right", "middle"] = "left"
    click_count: int = Field(default=1, ge=1)


class SelectStep(BaseStep):
    action: Literal["select"] = "select"
    selector: SelectorInfo
    option_value: str
    option_label: str | None = None


class CheckStep(BaseStep):
    action: Literal["check"] = "check"
    selector: SelectorInfo
    checked: bool


class HoverStep(BaseStep):
    action: Literal["hover"] = "hover"
    selector: SelectorInfo


class WaitStep(BaseStep):
    action: Literal["wait"] = "wait"
    wait_for: Literal["selector", "navigation", "network_idle", "timeout"]
    selector: SelectorInfo | None = None
    timeout_ms: int | None = Field(default=None, ge=0)
    state: Literal["attached", "detached", "visible", "hidden"] | None = None


class ExtractTextStep(BaseStep):
    action: Literal["extract_text"] = "extract_text"
    selector: SelectorInfo
    extracted_text: str
    output_variable: str | None = None


class ExtractAttributeStep(BaseStep):
    action: Literal["extract_attribute"] = "extract_attribute"
    selector: SelectorInfo
    attribute: str
    extracted_value: str | None
    output_variable: str | None = None


class ScrollStep(BaseStep):
    action: Literal["scroll"] = "scroll"
    selector: SelectorInfo | None = None
    delta_x: int | None = None
    delta_y: int | None = None


class PressKeyStep(BaseStep):
    action: Literal["press_key"] = "press_key"
    selector: SelectorInfo | None = None
    key: str


class ScreenshotStep(BaseStep):
    action: Literal["screenshot"] = "screenshot"
    filename: str


# ---------------------------------------------------------------------------
# Discriminated union — the Step type used in ActionLog.steps
# ---------------------------------------------------------------------------

Step = Annotated[
    Union[
        GotoStep,
        FillStep,
        ClickStep,
        SelectStep,
        CheckStep,
        HoverStep,
        WaitStep,
        ExtractTextStep,
        ExtractAttributeStep,
        ScrollStep,
        PressKeyStep,
        ScreenshotStep,
    ],
    Field(discriminator="action"),
]


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------


class SessionMetadata(BaseModel):
    """Session-level metadata block."""

    model_config = {"extra": "forbid"}

    session_id: str
    site: str
    start_url: str | None = None
    recorded_at: str  # ISO 8601 — validated by JSON Schema format check
    browserbot_version: str
    duration_seconds: float | None = Field(default=None, ge=0)
    step_count: int | None = Field(default=None, ge=0)
    workflow_hint: str | None = None

    @model_validator(mode="after")
    def step_count_matches_if_present(self) -> "SessionMetadata":
        # step_count cross-check is done at the ActionLog level.
        return self


# ---------------------------------------------------------------------------
# Root model — the complete Action Log
# ---------------------------------------------------------------------------


class ActionLog(BaseModel):
    """
    The complete Action Log for one recording session.

    This is the Python-native representation of a file that validates against
    docs/schemas/action_log_schema.json.
    """

    model_config = {"extra": "forbid"}

    schema_version: Literal["1.0"]
    metadata: SessionMetadata
    steps: list[Step] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_step_indices(self) -> "ActionLog":
        """Every step_index must equal its position in the list."""
        for i, step in enumerate(self.steps):
            if step.step_index != i:
                raise ValueError(
                    f"steps[{i}].step_index = {step.step_index}, expected {i}"
                )
        return self

    @model_validator(mode="after")
    def validate_step_count(self) -> "ActionLog":
        """metadata.step_count, if present, must equal len(steps)."""
        if (
            self.metadata.step_count is not None
            and self.metadata.step_count != len(self.steps)
        ):
            raise ValueError(
                f"metadata.step_count={self.metadata.step_count} "
                f"but steps has {len(self.steps)} items"
            )
        return self

    @classmethod
    def from_file(cls, path: str | Path) -> "ActionLog":
        """Load and parse an Action Log from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def to_file(self, path: str | Path, *, indent: int = 2) -> None:
        """Serialize this Action Log to a JSON file."""
        Path(path).write_text(
            self.model_dump_json(indent=indent, exclude_none=True),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# JSON Schema validator (jsonschema-based)
# ---------------------------------------------------------------------------


class ActionLogValidator:
    """
    Validates raw JSON dictionaries against the Action Log JSON Schema.

    Loads the schema once on construction and reuses it for all validations.
    This is faster than re-loading the schema file on every call.

    Usage::

        validator = ActionLogValidator()
        errors = validator.validate(data)
        if errors:
            raise ValueError(errors[0])
    """

    def __init__(self, schema_path: str | Path = SCHEMA_PATH) -> None:
        schema_text = Path(schema_path).read_text(encoding="utf-8")
        self._schema: dict[str, Any] = json.loads(schema_text)
        self._validator = jsonschema.Draft202012Validator(self._schema)
        log.debug(
            "ActionLogValidator loaded schema",
            extra={"schema_path": str(schema_path)},
        )

    def validate(self, data: dict[str, Any]) -> list[str]:
        """
        Validate a raw dict against the JSON Schema.

        Args:
            data: The parsed JSON object to validate.

        Returns:
            A list of error message strings.  Empty list = valid.
        """
        errors = sorted(
            self._validator.iter_errors(data),
            key=lambda e: list(e.absolute_path),
        )
        return [f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors]

    def validate_file(self, path: str | Path) -> list[str]:
        """
        Load a JSON file and validate it against the schema.

        Args:
            path: Path to the JSON file.

        Returns:
            A list of error message strings.  Empty list = valid.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.validate(data)

    def assert_valid(self, data: dict[str, Any], label: str = "data") -> None:
        """
        Validate and raise ValueError on the first error.

        Args:
            data:  The parsed JSON object to validate.
            label: A label to include in the error message for context.
        """
        errors = self.validate(data)
        if errors:
            raise ValueError(
                f"Action Log validation failed for {label!r}:\n"
                + "\n".join(f"  {e}" for e in errors)
            )
        log.debug("Action Log validation passed", extra={"label": label})
