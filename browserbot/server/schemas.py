"""
browserbot/server/schemas.py — Request/Response Pydantic schemas for REST API.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class RecordRequest(BaseModel):
    url: str | None = Field(default=None, description="Optional URL to start codegen with.")
    workflow_hint: str | None = Field(default=None, description="Optional hint describing the workflow.")


class SessionResponse(BaseModel):
    session_id: str
    stage: str
    created_at: str
    updated_at: str
    artifact_paths: dict[str, str] = Field(default_factory=dict)


class ParameterSchema(BaseModel):
    name: str
    example_value: Any
    log_step_index: int
    description: str
    is_sensitive: bool = False
    is_optional: bool = False


class ConfirmRequest(BaseModel):
    parameters: list[ParameterSchema] = Field(..., description="Confirmed parameters list.")


class GenerateRequest(BaseModel):
    output_dir: str | None = Field(default=None, description="Optional custom output directory.")


class PackageRequest(BaseModel):
    package_dir: str | None = Field(default=None, description="Optional custom package directory.")


class RegisterRequest(BaseModel):
    registry_config_path: str | None = Field(default=None, description="Optional custom Claude config path.")
