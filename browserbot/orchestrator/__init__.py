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

__all__ = [
    "OrchestrationPipeline",
    "PipelineOrchestrationError",
]

