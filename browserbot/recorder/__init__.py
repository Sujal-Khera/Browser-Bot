"""
browserbot.recorder — Browser workflow recorder.

Public API (Step 2.2 / 2.3):

    from browserbot.recorder.convert_codegen import convert_codegen_script, convert_codegen_file
    from browserbot.recorder.codegen_runner import run_recording_session

Entry point:

    python -m browserbot.recorder start [URL]
"""

from browserbot.recorder.convert_codegen import convert_codegen_file, convert_codegen_script
from browserbot.recorder.codegen_runner import run_recording_session

__all__ = [
    "convert_codegen_file",
    "convert_codegen_script",
    "run_recording_session",
]
