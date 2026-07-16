"""
browserbot/agents/pattern_extractor — Phase 3: Pattern Extraction.

Public API:

    from browserbot.agents.pattern_extractor import PatternExtractor, confirm_parameters
    from browserbot.agents.pattern_extractor import ExtractorOutput, ExtractedParameter, ConfirmedOutput

Entry point (dry-run demo):

    python -m browserbot.agents.pattern_extractor --dry-run <session.json>
    python -m browserbot.agents.pattern_extractor --backend ollama <session.json>
    python -m browserbot.agents.pattern_extractor --backend groq <session.json>
"""

from browserbot.agents.pattern_extractor.confirmer import ConfirmedOutput, confirm_parameters
from browserbot.agents.pattern_extractor.extractor import ExtractionError, PatternExtractor
from browserbot.agents.pattern_extractor.models import (
    ExtractedParameter,
    ExtractorOutput,
    ExtractorOutputValidator,
)

__all__ = [
    "PatternExtractor",
    "ExtractionError",
    "ExtractorOutput",
    "ExtractedParameter",
    "ExtractorOutputValidator",
    "confirm_parameters",
    "ConfirmedOutput",
]
