"""
browserbot/models/correction_payload.py — Step 5.3: Correction Payload model.

Defines the structure of the feedback payload sent back to the LLM
to guide script repair.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class CorrectionPayload(BaseModel):
    """Structured error context used to instruct the LLM on code correction."""

    model_config = {"extra": "forbid"}

    validation_stage: str  # e.g., "compilation", "import_check", "runtime_dry_run"
    failing_file: str  # e.g., "server.py"
    error_category: str  # e.g., "SyntaxError", "ImportError", "RuntimeError"
    exception: str  # The exception text or validation failure message
    validation_summary: str  # Short description of what failed
    relevant_code_snippet: Optional[str] = None  # Snippet around the failing block/line
