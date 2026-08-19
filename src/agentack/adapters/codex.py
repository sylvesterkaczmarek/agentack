from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable

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


def _account_ready(result: dict[str, Any]) -> tuple[bool, str]:
    account = result.get("account")
    requires_openai_auth = result.get("requiresOpenaiAuth")
    if isinstance(account, dict):
        return True, "Codex authentication is available."
    if requires_openai_auth is False:
        return True, "The configured Codex provider does not require OpenAI authentication."
    if requires_openai_auth is True:
        return False, "Codex CLI is installed but not authenticated. Run `codex login`, then retry."
    return False, "Codex App Server returned an ambiguous account state; AgentAck will not start a live probe."


def _probe_account_status(executable: str) -> tuple[bool, str]:
    """Read Codex auth state through the official local App Server without starting a model turn."""
    try:
        with tempfile.TemporaryDirectory(prefix="agentack-codex-account-") as directory:
            root = Path(directory)
            with CodexAppServer(executable, cwd=root, agentack_version=__version__) as server:
                result = server.request("account/read", {"refreshToken": False}, timeout=10)
        return _account_ready(result)
    except (OSError, CodexAppServerError, ValueError) as exc:
        return False, f"Codex App Server account preflight failed: {exc}"


class _ProbePolicyServer:
    """Delegate App Server traffic while pinning safe deterministic turn permissions for AgentAck probes."""

    def __init__(self, server: CodexAppServer, root: Path) -> None:
        self._server = server
        self._root = root.resolve()

    def request(self, method: str, params: dict[str, Any], *, timeout: float = 20) -> dict[str, Any]:
        if method == "turn/start":
            params = dict(params)
            params.update(
                {
                    "approvalPolicy": "untrusted",
                    "approvalsReviewer": "user",
                    "sandboxPolicy": {
                        "type": "workspaceWrite",
                        "writableRoots": [str(self._root)],
                        "networkAccess": False,
                        "excludeTmpdirEnvVar": False,
                        "excludeSlashTmp": False,
                    },
                }
            )
        return self._server.request(method, params, timeout=timeout)

    def next_message(self, *, timeout: float = 60) -> dict[str, Any]:
        return self._server.next_message(timeout=timeout)

    def respond(self, request_id: Any, result: dict[str, Any]) -> None:
        self._server.respond(request_id, result)

    def reject_unknown_request(self, request_id: Any) -> None:
        self._server.reject_unknown_request(request_id)


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
        if not supported:
            return AdapterStatus(
                name=self.name,
                display_name=self.display_name,
                installed=True,
                testable=False,
                executable=executable,
                version=version,
                detail=detail,
            )
        account_ready, account_detail = _probe_account_status(executable)
        return AdapterStatus(
            name=self.name,
            display_name=self.display_name,
            installed=True,
            testable=account_ready,
            executable=executable,
            version=version,
            detail=(
                "Live suite uses official Codex App Server approval, commandExecution, and turn/interrupt lifecycle evidence."
                if account_ready
                else account_detail
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
                        "Codex readiness",
                        "INCOMPLETE",
                        status.detail or "The installed Codex build is not ready for AgentAck's structured live probe.",
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
        print("AgentAck pins each turn to workspace-write + untrusted approval so synthetic writes must cross the approval gate.")
        print("AgentAck never sends acceptForSession or a persistent approval rule.\n")

        try:
            with tempfile.TemporaryDirectory(prefix="agentack-codex-") as directory:
                root = Path(directory)
                with CodexAppServer(status.executable, cwd=root, agentack_version=__version__) as raw_server:
                    account_result = raw_server.request("account/read", {"refreshToken": False}, timeout=10)
                    account_ready, account_detail = _account_ready(account_result)
                    if not account_ready:
                        return AdapterTestResult(
                            adapter=self.name,
                            display_name=self.display_name,
                            status="INCOMPLETE",
                            checks=(CheckResult("Codex authentication", "INCOMPLETE", account_detail),),
                            adapter_version=status.version,
                        )
                    server = _ProbePolicyServer(raw_server, root)
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
