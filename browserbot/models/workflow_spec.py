"""
browserbot/models/workflow_spec.py — Step 3.4: Workflow Spec data models and validator.

This module defines the Python representations of the Intermediate Representation
(IR) defined in docs/schemas/workflow_spec_schema.json.

decoupling "understanding the workflow" from "generating browser code".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import jsonschema
from pydantic import BaseModel, Field

from browserbot.logging import get_logger

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Path to the JSON Schema file
# ---------------------------------------------------------------------------

SCHEMA_PATH: Path = (
    Path(__file__).resolve().parents[2] / "docs" / "schemas" / "workflow_spec_schema.json"
)


# ---------------------------------------------------------------------------
# IR Models
# ---------------------------------------------------------------------------


class WorkflowMetadata(BaseModel):
    """Metadata about generation and session provenance."""

    model_config = {"extra": "forbid"}

    generator_version: str = Field(description="BrowserBot version used to generate the spec.")
    created_at: str = Field(description="ISO 8601 timestamp of spec generation.")
    source_session_id: str = Field(description="The session ID of the original recording.")


class WorkflowInfo(BaseModel):
    """High-level logical workflow details."""

    model_config = {"extra": "forbid"}

    site: str = Field(description="Domain where this workflow runs.")
    start_url: str = Field(description="Initial URL required to start.")
    description: str = Field(description="Human-readable description of the workflow purpose.")


class IRParameter(BaseModel):
    """A parameter that can be customized during execution of the generated tool."""

    model_config = {"extra": "forbid"}

    name: str = Field(description="Lowercase snake_case name of the parameter.")
    example_value: str = Field(description="Concrete value used as default or example.")
    log_step_index: int = Field(ge=0, description="Step index where this parameter is filled.")
    description: str | None = Field(default=None, description="Logical description of the input.")
    is_sensitive: bool = Field(default=False, description="True if value contains credentials/secrets.")
    is_optional: bool = Field(default=False, description="True if this parameter is optional.")


class IROutput(BaseModel):
    """Data extracted from the page during the workflow execution."""

    model_config = {"extra": "forbid"}

    name: str = Field(description="Lowercase snake_case name of the output variable.")
    log_step_index: int = Field(ge=0, description="Step index where the extraction occurred.")
    selector: dict[str, Any] = Field(description="Selector used to locate the text element.")
    description: str | None = Field(default=None, description="Logical description of what is extracted.")


class WorkflowSpec(BaseModel):
    """
    The canonical Intermediate Representation (IR) of a parameterized workflow.

    This class serves as the interface between the Pattern Extractor/UX phase
    and the downstream Code Generator phase.
    """

    model_config = {"extra": "forbid"}

    schema_version: Literal["1.0"] = "1.0"
    metadata: WorkflowMetadata
    workflow: WorkflowInfo
    steps: list[dict[str, Any]] = Field(description="Ordered steps from action log, possibly mapped to parameters.")
    parameters: list[IRParameter] = Field(default_factory=list, description="List of confirmed parameters.")
    fixed_step_indices: list[int] = Field(default_factory=list, description="Indices of fixed (static) steps.")
    outputs: list[IROutput] = Field(default_factory=list, description="Extracted workflow outputs.")

    @classmethod
    def from_file(cls, path: str | Path) -> WorkflowSpec:
        """Load and validate a WorkflowSpec from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        validator = WorkflowSpecValidator()
        validator.assert_valid(data, label=str(path))
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> None:
        """Serialize, validate against schema, and write to a JSON file."""
        data = self.model_dump(mode="json", exclude_none=True)
        validator = WorkflowSpecValidator()
        validator.assert_valid(data, label="serialize")
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("WorkflowSpec written to disk", extra={"path": str(path)})


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class WorkflowSpecValidator:
    """Validates raw dicts or files against the workflow_spec_schema.json."""

    def __init__(self, schema_path: str | Path = SCHEMA_PATH) -> None:
        schema_text = Path(schema_path).read_text(encoding="utf-8")
        self._schema: dict[str, Any] = json.loads(schema_text)
        self._validator = jsonschema.Draft202012Validator(self._schema)
        log.debug(
            "WorkflowSpecValidator loaded schema",
            extra={"schema_path": str(schema_path)},
        )

    def validate(self, data: dict[str, Any]) -> list[str]:
        """Validate raw dict against JSON Schema. Returns list of errors (empty if valid)."""
        errors = sorted(
            self._validator.iter_errors(data),
            key=lambda e: list(e.absolute_path),
        )
        return [f"{'.'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors]

    def assert_valid(self, data: dict[str, Any], label: str = "data") -> None:
        """Assert schema validity. Raises ValueError with details if invalid."""
        errors = self.validate(data)
        if errors:
            raise ValueError(
                f"Workflow Spec validation failed for {label!r}:\n"
                + "\n".join(f"  {e}" for e in errors)
            )
        log.debug("Workflow Spec validation passed", extra={"label": label})
