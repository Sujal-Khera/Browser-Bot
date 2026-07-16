"""
browserbot/agents/pattern_extractor/models.py — Step 3.1: Extractor output models.

These Pydantic models are the in-memory representation of the Pattern
Extractor's structured output.  They mirror the JSON Schema defined in
docs/schemas/extractor_output_schema.json.

Phase 3 Contract:
    The Pattern Extractor consumes an ActionLog and produces an
    ExtractorOutput. The Parameter Confirmation step (3.2) then receives
    an ExtractorOutput and returns a ConfirmedOutput.  Nothing downstream
    ever sees the raw ActionLog — only the confirmed ExtractorOutput.

The models deliberately contain NO Playwright-specific logic. They are
pure data containers that describe WHAT was extracted, not HOW to replay it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
from pydantic import BaseModel, Field

from browserbot.logging import get_logger

log = get_logger(__name__)

# Path to the extractor output JSON Schema
EXTRACTOR_SCHEMA_PATH: Path = (
    Path(__file__).resolve().parents[3] / "docs" / "schemas" / "extractor_output_schema.json"
)


# ---------------------------------------------------------------------------
# Pydantic models (mirrors JSON Schema)
# ---------------------------------------------------------------------------


class ExtractedParameter(BaseModel):
    """
    A single dynamic parameter identified by the Pattern Extractor.

    Attributes:
        name:           Snake_case parameter name (e.g. 'order_id').
        example_value:  The concrete value used in the recorded session.
        log_step_index: Which step_index in the ActionLog used this value.
        description:    Optional human-readable description.
        is_sensitive:   True if example_value is a scrubbed placeholder.
    """

    name: str
    example_value: str
    log_step_index: int
    description: str | None = None
    is_sensitive: bool = False

    model_config = {"frozen": True}


class ExtractorOutput(BaseModel):
    """
    The complete structured output of the Pattern Extractor.

    Produced by the LLM agent (Step 3.1) and consumed directly by the
    Parameter Confirmation step (Step 3.2).

    This object is schema-validated against extractor_output_schema.json
    before being used downstream — any malformed LLM output is rejected
    at this boundary.

    Attributes:
        parameters:          Dynamic parameters identified in the log.
        fixed_step_indices:  Step indices the LLM classified as fixed/structural.
        workflow_description: Optional one-sentence summary of the workflow.
    """

    parameters: list[ExtractedParameter] = Field(default_factory=list)
    fixed_step_indices: list[int] = Field(default_factory=list)
    workflow_description: str | None = None

    model_config = {"frozen": True}

    def model_dump_for_schema(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for schema validation."""
        return self.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# JSON Schema validator for ExtractorOutput
# ---------------------------------------------------------------------------


class ExtractorOutputValidator:
    """
    Validates a raw dict (parsed LLM JSON output) against the extractor
    output JSON Schema before constructing an ExtractorOutput.

    Mirrors the design of ActionLogValidator from Phase 2 — keeping the
    pattern consistent across all pipeline stages.
    """

    def __init__(self) -> None:
        import json
        with open(EXTRACTOR_SCHEMA_PATH, encoding="utf-8") as f:
            self._schema = json.load(f)
        self._registry = jsonschema.validators.validator_for(self._schema)

    def validate(self, data: dict[str, Any]) -> list[str]:
        """
        Validate data against the extractor output schema.

        Returns:
            A list of validation error messages.  Empty means valid.
        """
        validator = self._registry(self._schema)
        errors = [e.message for e in validator.iter_errors(data)]
        return errors

    def assert_valid(self, data: dict[str, Any], *, label: str = "") -> None:
        """
        Assert that data is valid.  Raises ValueError with all errors if not.
        """
        errors = self.validate(data)
        if errors:
            prefix = f"[{label}] " if label else ""
            raise ValueError(
                f"{prefix}Extractor output failed schema validation "
                f"({len(errors)} error(s)):\n" + "\n".join(f"  • {e}" for e in errors)
            )
        log.debug(
            "Extractor output schema validation passed",
            extra={"label": label or "(no label)"},
        )

    def parse(self, data: dict[str, Any], *, label: str = "") -> ExtractorOutput:
        """
        Validate and parse a dict into an ExtractorOutput.

        Raises:
            ValueError: If the data does not conform to the schema.
        """
        self.assert_valid(data, label=label)
        return ExtractorOutput.model_validate(data)
