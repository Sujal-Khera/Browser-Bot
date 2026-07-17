"""
browserbot/models/package.py — Step 6.1 Package manifest models and validator.

Defines the Python representation and validator for the auto-generated
package manifest (browserbot_package.json) contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

import jsonschema
from pydantic import BaseModel, Field

from browserbot.logging import get_logger

log = get_logger(__name__)

# Path to the JSON Schema
SCHEMA_PATH: Path = (
    Path(__file__).resolve().parents[2] / "docs" / "schemas" / "package_schema.json"
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ClaudeConfigSnippet(BaseModel):
    model_config = {"extra": "forbid"}

    command: str
    args: list[str]
    env: dict[str, str] = Field(default_factory=dict)


class PackageMetadata(BaseModel):
    model_config = {"extra": "forbid"}

    browserbot_version: str
    generated_at: str  # ISO 8601 UTC
    source_session_id: str
    site: str


class BrowserBotPackage(BaseModel):
    """The auto-generated package manifest detailing an installable BrowserBot package."""

    model_config = {"extra": "forbid"}

    package_version: Literal["1.0"] = "1.0"
    package_name: str
    entry_point: Literal["server.py"] = "server.py"
    dependencies: list[str]
    claude_config_snippet: ClaudeConfigSnippet
    metadata: PackageMetadata

    @classmethod
    def from_file(cls, path: str | Path) -> BrowserBotPackage:
        """Load and validate a package manifest from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        validator = BrowserBotPackageValidator()
        validator.assert_valid(data, label=str(path))
        return cls.model_validate(data)

    def to_file(self, path: str | Path) -> None:
        """Serialize, validate against schema, and write to a JSON file."""
        data = self.model_dump(mode="json", exclude_none=True)
        validator = BrowserBotPackageValidator()
        validator.assert_valid(data, label="serialize")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
        log.info("BrowserBotPackage written to disk", extra={"path": str(path)})


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class BrowserBotPackageValidator:
    """Validates raw dicts or files against the package_schema.json."""

    def __init__(self, schema_path: str | Path = SCHEMA_PATH) -> None:
        schema_text = Path(schema_path).read_text(encoding="utf-8")
        self._schema: dict[str, Any] = json.loads(schema_text)
        self._validator = jsonschema.Draft202012Validator(self._schema)
        log.debug(
            "BrowserBotPackageValidator loaded schema",
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
        """Assert schema validity. Raises ValueError if invalid."""
        errors = self.validate(data)
        if errors:
            raise ValueError(
                f"BrowserBot Package Manifest validation failed for {label!r}:\n"
                + "\n".join(f"  {e}" for e in errors)
            )
        log.debug("BrowserBot Package Manifest validation passed", extra={"label": label})
