"""
browserbot/agents/validator — Phase 5: Verification & Dry-Run.

Public API:

    from browserbot.agents.validator import DryRunHarness, ValidationPipeline
"""

from browserbot.agents.validator.harness import DryRunHarness, DryRunResult
from browserbot.agents.validator.pipeline import ValidationPipeline

__all__ = [
    "DryRunHarness",
    "DryRunResult",
    "ValidationPipeline",
]
