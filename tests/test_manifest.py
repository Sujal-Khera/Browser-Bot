"""
tests/test_manifest.py — Step 4.3 automated tests.

Validates tool manifest generation and schema correctness.
No LLM connection required.

Run:
    python -m pytest tests/test_manifest.py -v
"""

from __future__ import annotations

from pathlib import Path
import pytest

from browserbot.agents.code_generator.manifest import generate_manifest
from browserbot.models.mcp_tool import MCPToolManifest, MCPToolManifestValidator
from browserbot.models.workflow_spec import WorkflowSpec

FIXTURE_SINGLE = Path(__file__).parent / "fixtures" / "session_single_param.json"


def _load_spec_from_session() -> WorkflowSpec:
    """Helper to mock a WorkflowSpec directly from single parameter session fixture log."""
    from browserbot.models.action_log import ActionLog
    from browserbot.agents.pattern_extractor.generator import generate_workflow_spec
    from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput
    from browserbot.agents.pattern_extractor.models import ExtractedParameter
    
    log = ActionLog.from_file(FIXTURE_SINGLE)
    confirmed = ConfirmedOutput(
        parameters=[
            ExtractedParameter(
                name="search_query",
                example_value="learning agents",
                log_step_index=1,
                description="The search term to query",
                is_sensitive=False,
                is_optional=False,
            )
        ],
        fixed_step_indices=[0, 2],
        workflow_description="Search for a query on example.com",
    )
    return generate_workflow_spec(log, confirmed)


# ---------------------------------------------------------------------------
# Test 1: Successful Manifest Generation and Validation
# ---------------------------------------------------------------------------


def test_manifest_generation_success() -> None:
    spec = _load_spec_from_session()
    manifest = generate_manifest(spec)

    assert isinstance(manifest, MCPToolManifest)
    assert manifest.schema_version == "1.0"
    assert manifest.mcp_tool_name.startswith("execute_")
    assert "example_com" in manifest.mcp_tool_name
    assert manifest.description == "Search for a query on example.com"
    
    # Check parameters schema
    param_schema = manifest.parameters_schema
    assert param_schema.type == "object"
    assert "search_query" in param_schema.properties
    
    prop = param_schema.properties["search_query"]
    assert prop.type == "string"
    assert prop.description == "The search term to query"
    assert prop.default == "learning agents"
    assert prop.is_sensitive is False
    
    assert "search_query" in param_schema.required
    
    # Check metadata
    assert manifest.metadata.site == "example.com"
    assert manifest.metadata.source_session_id == "session_single_param_20260716T120000"
    
    # Run JSON Schema validation check
    validator = MCPToolManifestValidator()
    errors = validator.validate(manifest.model_dump(mode="json", exclude_none=True))
    assert errors == [], f"Manifest validation failed: {errors}"


# ---------------------------------------------------------------------------
# Test 2: Schema validation rejects malformed manifest dicts
# ---------------------------------------------------------------------------


def test_manifest_validator_rejects_invalid_manifest() -> None:
    validator = MCPToolManifestValidator()

    # Missing mcp_tool_name
    bad_data_1 = {
        "schema_version": "1.0",
        "description": "Fails",
        "parameters_schema": {
            "type": "object",
            "properties": {}
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-16T12:00:00Z",
            "source_session_id": "session_123",
            "site": "example.com"
        }
    }
    errors = validator.validate(bad_data_1)
    assert len(errors) > 0
    assert any("mcp_tool_name" in err for err in errors)

    # Wrong schema_version
    bad_data_2 = {
        "schema_version": "2.0",
        "mcp_tool_name": "execute_test",
        "description": "Fails",
        "parameters_schema": {
            "type": "object",
            "properties": {}
        },
        "metadata": {
            "browserbot_version": "0.1.0",
            "generated_at": "2026-07-16T12:00:00Z",
            "source_session_id": "session_123",
            "site": "example.com"
        }
    }
    errors = validator.validate(bad_data_2)
    assert len(errors) > 0
    assert any("schema_version" in err for err in errors)


def test_derive_tool_name_with_and_without_hint() -> None:
    from browserbot.agents.code_generator.manifest import derive_tool_name

    # Default description / No hint
    assert derive_tool_name("nobuycart.com", None) == "execute_nobuycart_com"
    assert derive_tool_name("nobuycart.com", "Automated browser workflow on nobuycart.com") == "execute_nobuycart_com"

    # Custom hint
    assert derive_tool_name("nobuycart.com", "Order status lookup") == "execute_order_status_lookup_nobuycart_com"
    assert derive_tool_name("example.com", "Track Package #123") == "execute_track_package_123_example_com"

