from __future__ import annotations

import shutil

from .base import AdapterStatus, AdapterTestResult, AgentAdapter, CheckResult
from .codex_protocol import safe_version

_CODEX_LIVE_LIMITATION = (
    "Codex CLI is installed, but AgentAck does not currently expose a verified deterministic live approval-integrity test. "
    "Real-binary testing against Codex CLI 0.148.0 did not produce a reproducible standalone human command-approval "
    "boundary through the public App Server path, so Codex remains detection and deterministic-trace coverage only."
)


class CodexCLIAdapter(AgentAdapter):
    """Detect Codex while keeping live approval claims fail-closed."""

    name = "codex"
    display_name = "Codex CLI"

    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable

    def detect(self) -> AdapterStatus:
        executable = self.executable or shutil.which("codex")
        if not executable:
            return AdapterStatus(
                name=self.name,
                display_name=self.display_name,
                installed=False,
                testable=False,
                detail="Install Codex CLI for detection. AgentAck does not currently expose a verified Codex live test.",
            )
        return AdapterStatus(
            name=self.name,
            display_name=self.display_name,
            installed=True,
            testable=False,
            executable=executable,
            version=safe_version(executable),
            detail=_CODEX_LIVE_LIMITATION,
        )

    def run_test(self) -> AdapterTestResult:
        status = self.detect()
        detail = (
            _CODEX_LIVE_LIMITATION
            if status.installed
            else "The `codex` executable was not found on PATH. AgentAck does not currently expose a verified Codex live test."
        )
        return AdapterTestResult(
            adapter=self.name,
            display_name=self.display_name,
            status="INCOMPLETE",
            checks=(CheckResult("Codex live approval boundary", "INCOMPLETE", detail),),
            notes=(
                "Codex App Server protocol parsing, fixtures, and deterministic analysis remain in the repository for future support.",
                "Use `agentack coverage` for the current trace/live coverage matrix.",
            ),
            adapter_version=status.version,
        )


__all__ = ["CodexCLIAdapter"]
