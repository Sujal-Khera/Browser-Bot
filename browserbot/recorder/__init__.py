"""
browserbot.recorder — Browser workflow recorder.

Public API (Step 2.2 / 2.3 / 2.4):

    from browserbot.recorder.convert_codegen import convert_codegen_script, convert_codegen_file
    from browserbot.recorder.codegen_runner import run_recording_session
    from browserbot.recorder.scrubber import scrub, Scrubber, ScrubResult

Entry point:

    python -m browserbot.recorder start [URL]
"""

from browserbot.recorder.convert_codegen import convert_codegen_file, convert_codegen_script
from browserbot.recorder.codegen_runner import run_recording_session
from browserbot.recorder.scrubber import Scrubber, ScrubResult, scrub

__all__ = [
    "convert_codegen_file",
    "convert_codegen_script",
    "run_recording_session",
    "scrub",
    "Scrubber",
    "ScrubResult",
]

