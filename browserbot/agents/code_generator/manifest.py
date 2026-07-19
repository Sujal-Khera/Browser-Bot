"""
browserbot/agents/code_generator/manifest.py — Step 4.3: Manifest Generator.

Translates the WorkflowSpec IR into a schema-valid, deterministic
MCPToolManifest detailing the tool metadata and parameter schema.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from browserbot import __version__
from browserbot.logging import get_logger
from browserbot.models.mcp_tool import (
    ManifestMetadata,
    MCPToolManifest,
    ParameterProperty,
    ParametersSchema,
)
from browserbot.models.workflow_spec import WorkflowSpec

log = get_logger(__name__)


def derive_tool_name(site: str, description: str | None = None) -> str:
    """
    Derive an MCP tool name from site hostname and optional workflow description/hint.
    Falls back to `execute_{normalized_site}` when hint is absent or default.
    """
    normalized_site = re.sub(r"[^a-zA-Z0-9]", "_", site).lower().strip("_")
    default_desc = f"Automated browser workflow on {site}"

    if description and description.strip() and description.strip() != default_desc:
        hint_slug = re.sub(r"[^a-zA-Z0-9]", "_", description.lower()).strip("_")
        hint_slug = re.sub(r"_+", "_", hint_slug)
        if hint_slug:
            if len(hint_slug) > 30:
                hint_slug = hint_slug[:30].rsplit("_", 1)[0]
            if hint_slug.endswith(normalized_site):
                return f"execute_{hint_slug}"
            return f"execute_{hint_slug}_{normalized_site}"

    return f"execute_{normalized_site}"


def generate_manifest(spec: WorkflowSpec) -> MCPToolManifest:
    """
    Generate the deterministic tool manifest for an IR specification.

    Args:
        spec: The validated WorkflowSpec IR.

    Returns:
        A validated MCPToolManifest object.
    """
    log.info(
        "Generating MCPToolManifest",
        extra={
            "site": spec.workflow.site,
            "source_session": spec.metadata.source_session_id,
        },
    )

    # 1. Normalize tool name using derive_tool_name (supports hint & fallback)
    tool_name = derive_tool_name(spec.workflow.site, spec.workflow.description)

    # 2. Build metadata
    metadata = ManifestMetadata(
        browserbot_version=__version__,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_session_id=spec.metadata.source_session_id,
        site=spec.workflow.site,
    )

    # 3. Build parameter schema properties
    properties: dict[str, ParameterProperty] = {}
    required: list[str] = []

    for param in spec.parameters:
        desc = param.description or f"Input field parameter '{param.name}'"
        properties[param.name] = ParameterProperty(
            type="string",
            description=desc,
            default=param.example_value,
            is_sensitive=param.is_sensitive,
        )
        if not param.is_optional:
            required.append(param.name)

    param_schema = ParametersSchema(
        type="object",
        properties=properties,
        required=required,
    )

    # 4. Construct manifest
    manifest = MCPToolManifest(
        schema_version="1.0",
        mcp_tool_name=tool_name,
        description=spec.workflow.description,
        parameters_schema=param_schema,
        metadata=metadata,
    )

    log.info(
        "MCPToolManifest generation complete",
        extra={
            "tool_name": tool_name,
            "parameters": len(properties),
            "required": len(required),
        },
    )
    return manifest
