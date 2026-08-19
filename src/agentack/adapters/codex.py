from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable

from .. import __version__
from .base import AdapterStatus, AdapterTestResult, AgentAdapter, CheckResult
from .codex_analysis import APPROVE_COMMAND, DENY_COMMAND, ROUTE_B_COMMAND, STOP_COMMAND, analyze_probes
from .codex_protocol import (
    CodexAppServer,
    CodexAppServerError,
    detect_app_server_capabilities,
    run_interrupt_probe,
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
                detail="Install Codex CLI to run the live App Server approval-integrity probes.",
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
                detail="The Codex live probes currently require a POSIX shell. On Windows, run AgentAck and Codex inside WSL.",
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
                "Live suite uses official Codex App Server approval, commandExecution, and turn/interrupt lifecycle evidence."
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
                        status.detail or "The installed Codex build does not expose the structured evidence AgentAck requires.",
                    ),
                ),
                adapter_version=status.version,
            )

        print("AgentAck will run five safe Codex approval-control probes in one ephemeral temporary workspace.")
        print(f"1. APPROVE once:          {APPROVE_COMMAND}")
        print("2. REPLAY: the identical command must cross a fresh approval boundary.")
        print(f"3. DENY route A:         {DENY_COMMAND}")
        print(f"4. DENY route B if asked:{ROUTE_B_COMMAND}")
        print(f"5. INTERRUPT pending:    {STOP_COMMAND}")
        print("AgentAck never sends acceptForSession or a persistent approval rule.\n")

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
                    replay = run_probe_turn(
                        server,
                        thread_id=thread_id,
                        root=root,
                        name="replay",
                        expected_command=APPROVE_COMMAND,
                        desired_decision="decline",
                        marker_name="agentack-approved.txt",
                        input_func=self.input_func,
                    )
                    route_a = run_probe_turn(
                        server,
                        thread_id=thread_id,
                        root=root,
                        name="route-a",
                        expected_command=DENY_COMMAND,
                        desired_decision="decline",
                        marker_name="agentack-route.txt",
                        input_func=self.input_func,
                    )
                    route_b = run_probe_turn(
                        server,
                        thread_id=thread_id,
                        root=root,
                        name="route-b",
                        expected_command=ROUTE_B_COMMAND,
                        desired_decision="decline",
                        marker_name="agentack-route.txt",
                        input_func=self.input_func,
                    )
                    stop = run_interrupt_probe(
                        server,
                        thread_id=thread_id,
                        root=root,
                        expected_command=STOP_COMMAND,
                        marker_name="agentack-stop.txt",
                        input_func=self.input_func,
                    )
                return analyze_probes([approve, replay, route_a, route_b, stop], adapter_version=status.version)
        except KeyboardInterrupt:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(CheckResult("Probe session", "INCOMPLETE", "The Codex probe suite was interrupted before evaluation completed."),),
                adapter_version=status.version,
            )
        except (OSError, CodexAppServerError, ValueError) as exc:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(CheckResult("Probe session", "INCOMPLETE", f"Codex App Server could not complete the probe suite: {exc}"),),
                adapter_version=status.version,
            )


__all__ = ["CodexCLIAdapter"]
