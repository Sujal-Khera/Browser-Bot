"""
browserbot/agents/code_generator — Phase 4: Code Generation.

Public API:

    from browserbot.agents.code_generator import CodeGenerator, validate_dsl, DSLValidationError
"""

from browserbot.agents.code_generator.generator import CodeGenerator
from browserbot.agents.code_generator.validator import DSLValidationError, validate_dsl
from browserbot.agents.code_generator.manifest import generate_manifest
from browserbot.agents.code_generator.coordinator import PipelineCoordinator

__all__ = [
    "CodeGenerator",
    "validate_dsl",
    "DSLValidationError",
    "generate_manifest",
    "PipelineCoordinator",
]
