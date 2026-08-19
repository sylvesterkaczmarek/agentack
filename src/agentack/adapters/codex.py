from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .. import __version__
from .base import AdapterStatus, AdapterTestResult, AgentAdapter, CheckResult
from .codex_analysis import APPROVE_COMMAND, DENY_COMMAND, analyze_probes
from .codex_protocol import (
    CodexAppServer,
    CodexAppServerError,
    detect_app_server_capabilities,
    run_probe_turn,
    safe_version,
    start_ephemeral_thread,
)


class CodexCLIAdapter(AgentAdapter):
    name = "codex"
    display_name = "Codex CLI"

    def __init__(self, executable: str | None = None, *, input_func: Callable[[str], str] = input) -> None:
        self.executable = executable
        self.input_func = input_func

    def detect(self) -> AdapterStatus:
        executable = self.executable or shutil.which("codex")
        if not executable:
            return AdapterStatus(
                name=self.name,
                display_name=self.display_name,
                installed=False,
                testable=False,
                detail="Install Codex CLI to run the live App Server approval-integrity probe.",
            )
        version = safe_version(executable)
        if os.name == "nt":
            return AdapterStatus(
                name=self.name,
                display_name=self.display_name,
                installed=True,
                testable=False,
                executable=executable,
                version=version,
                detail="The Codex live probe currently requires a POSIX shell. On Windows, run AgentAck and Codex inside WSL.",
            )
        supported, detail = detect_app_server_capabilities(executable)
        return AdapterStatus(
            name=self.name,
            display_name=self.display_name,
            installed=True,
            testable=supported,
            executable=executable,
            version=version,
            detail=(
                "Live test uses the official Codex App Server command approval request and authoritative commandExecution lifecycle."
                if supported
                else detail
            ),
        )

    def run_test(self) -> AdapterTestResult:
        status = self.detect()
        if not status.installed or not status.executable:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(CheckResult("Codex CLI installed", "INCOMPLETE", "The `codex` executable was not found on PATH."),),
                notes=("Run `agentack doctor` after installing Codex CLI.",),
                adapter_version=status.version,
            )
        if not status.testable:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(
                    CheckResult(
                        "Codex App Server capability",
                        "INCOMPLETE",
                        status.detail or "The installed Codex build does not expose the structured approval evidence AgentAck requires.",
                    ),
                ),
                adapter_version=status.version,
            )

        print("AgentAck will start an ephemeral Codex App Server thread in a temporary read-only workspace.")
        print("You will make two real human decisions through AgentAck's local terminal client:")
        print(f"1. APPROVE: {APPROVE_COMMAND}")
        print(f"2. DENY:    {DENY_COMMAND}")
        print("AgentAck sends those decisions to Codex's official approval protocol.")
        print("This tests App Server approval/enforcement, not the Codex TUI or VS Code approval-card rendering.\n")

        try:
            with tempfile.TemporaryDirectory(prefix="agentack-codex-") as directory:
                root = Path(directory)
                with CodexAppServer(status.executable, cwd=root, agentack_version=__version__) as server:
                    thread_id = start_ephemeral_thread(server, root)
                    approve = run_probe_turn(
                        server,
                        thread_id=thread_id,
                        root=root,
                        name="approve",
                        expected_command=APPROVE_COMMAND,
                        desired_decision="accept",
                        marker_name="agentack-approved.txt",
                        input_func=self.input_func,
                    )
                    deny = run_probe_turn(
                        server,
                        thread_id=thread_id,
                        root=root,
                        name="deny",
                        expected_command=DENY_COMMAND,
                        desired_decision="decline",
                        marker_name="agentack-denied.txt",
                        input_func=self.input_func,
                    )
                return analyze_probes([approve, deny], adapter_version=status.version)
        except KeyboardInterrupt:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(CheckResult("Probe session", "INCOMPLETE", "The Codex probe was interrupted before evaluation completed."),),
                adapter_version=status.version,
            )
        except (OSError, CodexAppServerError, ValueError) as exc:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(CheckResult("Probe session", "INCOMPLETE", f"Codex App Server could not complete the probe: {exc}"),),
                adapter_version=status.version,
            )


__all__ = ["CodexCLIAdapter"]
