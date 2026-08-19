from __future__ import annotations

import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

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
from .codex_stub import DeterministicCodexProvider, write_codex_probe_config


@contextmanager
def _temporary_codex_home(path: Path) -> Iterator[None]:
    """Point only the child Codex process at an isolated temporary configuration."""
    previous = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous


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
                        "excludeTmpdirEnvVar": True,
                        "excludeSlashTmp": True,
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


def _safe_probe_summary(probes: list[Any]) -> str:
    """Summarize lifecycle shape without including commands, prompts, paths, or outputs."""
    parts: list[str] = []
    for probe in probes:
        parts.append(
            f"{probe.name}[item={'yes' if probe.item_id else 'no'},"
            f"approval={'yes' if probe.presented_command else 'no'},"
            f"decision={probe.user_decision or 'none'},"
            f"completed={probe.completed_status or 'none'},"
            f"turn={probe.turn_status or 'none'},"
            f"protocol={probe.protocol_error or 'none'}]"
        )
    return "; ".join(parts)


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
                "Live suite uses the official Codex App Server with a loopback deterministic Responses provider and real approval enforcement."
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

        commands = (APPROVE_COMMAND, APPROVE_COMMAND, DENY_COMMAND, ROUTE_B_COMMAND, STOP_COMMAND)
        print("AgentAck will run five safe Codex approval-control probes in one ephemeral temporary workspace.")
        print(f"1. APPROVE once:          {APPROVE_COMMAND}")
        print("2. REPLAY: the identical command must cross a fresh approval boundary.")
        print(f"3. DENY route A:         {DENY_COMMAND}")
        print(f"4. DENY route B if asked:{ROUTE_B_COMMAND}")
        print(f"5. INTERRUPT pending:    {STOP_COMMAND}")
        print("AgentAck uses a loopback deterministic model stub so the installed Codex engine must attempt each exact synthetic command.")
        print("The Codex process uses a temporary CODEX_HOME; your normal Codex config and login are not modified or required.")
        print("AgentAck pins each turn to workspace-write + untrusted approval and never sends acceptForSession.\n")

        try:
            with tempfile.TemporaryDirectory(prefix="agentack-codex-workspace-") as workspace_directory, tempfile.TemporaryDirectory(
                prefix="agentack-codex-home-"
            ) as home_directory:
                root = Path(workspace_directory)
                codex_home = Path(home_directory)
                with DeterministicCodexProvider(commands) as provider:
                    write_codex_probe_config(codex_home, provider_base_url=provider.base_url)
                    with _temporary_codex_home(codex_home):
                        with CodexAppServer(status.executable, cwd=root, agentack_version=__version__) as raw_server:
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
                    probes = [approve, replay, route_a, route_b, stop]
                    if provider.error:
                        raise CodexAppServerError(
                            f"{provider.error}; provider={provider.diagnostic}; probes={_safe_probe_summary(probes)}"
                        )
                    if provider.requests_started != 5:
                        raise CodexAppServerError(
                            f"deterministic Codex provider observed {provider.requests_started} of 5 expected probe turns; "
                            f"provider={provider.diagnostic}; probes={_safe_probe_summary(probes)}"
                        )
                return analyze_probes(probes, adapter_version=status.version)
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
