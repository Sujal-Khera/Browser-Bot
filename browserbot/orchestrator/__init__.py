"""
browserbot.orchestrator — pipeline coordinator (Step 7.1 concept).

The orchestrator loads configuration, invokes pipeline stages in order,
manages execution state, handles retries, and surfaces structured errors.
It owns no business logic — only sequencing.
"""

from browserbot.orchestrator.pipeline import (
    OrchestrationPipeline,
    PipelineOrchestrationError,
)
from browserbot.orchestrator.self_healing import self_heal_package

__all__ = [
    "OrchestrationPipeline",
    "PipelineOrchestrationError",
    "self_heal_package",
]

