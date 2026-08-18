"""Claude Code adapter public facade."""

import shutil  # noqa: F401
import subprocess  # noqa: F401

from . import claude_live as _live
from .claude_analysis import analyze_capture
from .claude_capture import claude_action, read_capture, record_hook_event
from .otel import extract_tool_decisions


class ClaudeCodeAdapter(_live.ClaudeCodeAdapter):
    """Stable facade for the split Claude adapter implementation."""

    def run_test(self):  # type: ignore[no-untyped-def]
        # Keep the historical facade patch points usable by tests and downstream
        # harnesses while implementation responsibilities live in smaller modules.
        old_read = _live.read_capture
        old_extract = _live.extract_tool_decisions
        _live.read_capture = read_capture
        _live.extract_tool_decisions = extract_tool_decisions
        try:
            return super().run_test()
        finally:
            _live.read_capture = old_read
            _live.extract_tool_decisions = old_extract


build_settings = _live.build_settings

__all__ = [
    "ClaudeCodeAdapter",
    "analyze_capture",
    "build_settings",
    "claude_action",
    "read_capture",
    "record_hook_event",
]
