"""
browserbot/models/validation_report.py — Step 5.1/5.2 Validation Report models.

Defines the Pydantic model for structured validation reports produced by
the verification pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from browserbot.logging import get_logger

log = get_logger(__name__)


class StageResult(BaseModel):
    """Result of a single validation stage."""

    model_config = {"extra": "forbid"}

    success: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    """Validation report containing the status of all validation layers."""

    model_config = {"extra": "forbid"}

    schema_version: str = "1.0"
    generated_at: str  # ISO 8601 UTC timestamp
    tool_dir: str
    overall_success: bool

    file_existence: StageResult
    compilation: StageResult
    import_check: StageResult
    runtime_dry_run: StageResult

    @classmethod
    def from_file(cls, path: str | Path) -> ValidationReport:
        """Load and deserialize validation report from JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> None:
        """Serialize validation report and write to JSON file."""
        data = self.model_dump(mode="json")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("Validation report written to disk", extra={"path": str(path)})
