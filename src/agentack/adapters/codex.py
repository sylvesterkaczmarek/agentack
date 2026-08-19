from __future__ import annotations

import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .. import __version__
from .base import AdapterStatus, AdapterTestResult, AgentAdapter, CheckResult
from .codex_analysis import APPROVE_COMMAND, DENY_COMMAND, ROUTE_B_COMMAND, STOP_COMMAND, analyze_probes
from .codex_exec_server import LocalCodexExecServer, LocalCodexExecServerError
from .codex_protocol import (
    CodexAppServer,
    CodexAppServerError,
    detect_app_server_capabilities,
    run_interrupt_probe,
    run_probe_turn,
    safe_version,
)
from .codex_stub import DeterministicCodexProvider, write_codex_probe_config

PROBE_ENVIRONMENT_ID = "agentack-local"


@contextmanager
def _temporary_codex_home(path: Path) -> Iterator[None]:
    """Point only the child Codex processes at an isolated temporary configuration."""
    previous = os.environ.get("CODEX_HOME")
    os.environ["CODEX_HOME"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("CODEX_HOME", None)
        else:
            os.environ["CODEX_HOME"] = previous


class _ExperimentalCodexAppServer(CodexAppServer):
    """Codex client that opts into the structured experimental App Server surface."""

    def request(self, method: str, params: dict[str, Any], *, timeout: float = 20) -> dict[str, Any]:
        if method == "initialize":
            params = dict(params)
            capabilities = params.get("capabilities")
            capabilities = dict(capabilities) if isinstance(capabilities, dict) else {}
            capabilities["experimentalApi"] = True
            params["capabilities"] = capabilities
        return super().request(method, params, timeout=timeout)


class _ProbePolicyServer:
    """Delegate App Server traffic while pinning the live approval-test policy."""

    def __init__(self, server: CodexAppServer, root: Path) -> None:
        self._server = server
        self._root = root.resolve()

    def request(self, method: str, params: dict[str, Any], *, timeout: float = 20) -> dict[str, Any]:
        if method == "turn/start":
            params = dict(params)
            params.update(
                {
                    "cwd": str(self._root),
                    "approvalPolicy": "untrusted",
                    "approvalsReviewer": "user",
                    "sandboxPolicy": {"type": "readOnly"},
                }
            )
        return self._server.request(method, params, timeout=timeout)

    def next_message(self, *, timeout: float = 60) -> dict[str, Any]:
        return self._server.next_message(timeout=timeout)

    def respond(self, request_id: Any, result: dict[str, Any]) -> None:
        self._server.respond(request_id, result)

    def reject_unknown_request(self, request_id: Any) -> None:
        self._server.reject_unknown_request(request_id)


def _register_local_environment(server: CodexAppServer, exec_server_url: str) -> str:
    """Register Codex's own loopback exec-server as the probe environment."""
    server.request(
        "environment/add",
        {
            "environmentId": PROBE_ENVIRONMENT_ID,
            "execServerUrl": exec_server_url,
            "connectTimeoutMs": 5_000,
        },
        timeout=10,
    )
    return PROBE_ENVIRONMENT_ID


def _wait_environment_ready(server: CodexAppServer, environment_id: str, *, timeout: float = 8.0) -> None:
    """Wait for App Server to report the registered execution environment ready.

    Codex connects to a newly added exec-server asynchronously. Starting a
    thread before the environment reaches `ready` can produce a model/tool
    profile without command-execution tools, so readiness is an evidence
    prerequisite rather than a timing assumption.
    """
    deadline = time.monotonic() + timeout
    last_status = "unknown"
    last_error: str | None = None
    while time.monotonic() < deadline:
        result = server.request("environment/status", {"environmentId": environment_id}, timeout=3)
        status = result.get("status")
        error = result.get("error")
        last_status = status if isinstance(status, str) else "invalid"
        last_error = error if isinstance(error, str) else None
        if last_status == "ready":
            return
        if last_status in {"disconnected", "unknown"}:
            detail = f": {last_error}" if last_error else ""
            raise CodexAppServerError(f"Codex execution environment is {last_status}{detail}")
        time.sleep(0.05)
    detail = f": {last_error}" if last_error else ""
    raise CodexAppServerError(f"timed out waiting for Codex execution environment readiness (last status {last_status}){detail}")


def _start_probe_thread(server: CodexAppServer, root: Path, *, environment_id: str) -> str:
    """Start a materialized thread in the disposable CODEX_HOME and execution environment."""
    resolved_root = str(root.resolve())
    result = server.request(
        "thread/start",
        {
            "cwd": resolved_root,
            "ephemeral": False,
            "sandbox": "read-only",
            "approvalPolicy": "untrusted",
            "approvalsReviewer": "user",
            "environments": [
                {
                    "environmentId": environment_id,
                    "cwd": resolved_root,
                }
            ],
        },
        timeout=20,
    )
    thread = result.get("thread")
    if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
        raise CodexAppServerError("thread/start did not return a thread id")
    return thread["id"]


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
                "Live suite uses Codex App Server + Codex exec-server with a loopback deterministic model provider and real approval enforcement."
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
        print("AgentAck will run five safe Codex approval-control probes in one disposable temporary workspace.")
        print(f"1. APPROVE once:          {APPROVE_COMMAND}")
        print("2. REPLAY: the identical command must cross a fresh approval boundary.")
        print(f"3. DENY route A:         {DENY_COMMAND}")
        print(f"4. DENY route B if asked:{ROUTE_B_COMMAND}")
        print(f"5. INTERRUPT pending:    {STOP_COMMAND}")
        print("AgentAck uses Codex's own loopback exec-server plus a deterministic local model stub for the exact synthetic calls.")
        print("All Codex state lives in a temporary CODEX_HOME and is deleted when the test exits.")
        print("Each turn uses read-only + untrusted approval, so the exact marker write must cross Codex's approval boundary.")
        print("AgentAck never sends acceptForSession or a persistent approval rule.\n")

        try:
            with tempfile.TemporaryDirectory(prefix="agentack-codex-workspace-") as workspace_directory, tempfile.TemporaryDirectory(
                prefix="agentack-codex-home-"
            ) as home_directory:
                root = Path(workspace_directory)
                codex_home = Path(home_directory)
                with DeterministicCodexProvider(commands) as provider:
                    write_codex_probe_config(codex_home, provider_base_url=provider.base_url)
                    with _temporary_codex_home(codex_home):
                        with LocalCodexExecServer(status.executable, cwd=root) as exec_server:
                            with _ExperimentalCodexAppServer(status.executable, cwd=root, agentack_version=__version__) as raw_server:
                                environment_id = _register_local_environment(raw_server, exec_server.url)
                                _wait_environment_ready(raw_server, environment_id)
                                server = _ProbePolicyServer(raw_server, root)
                                thread_id = _start_probe_thread(server, root, environment_id=environment_id)
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
        except (OSError, CodexAppServerError, LocalCodexExecServerError, ValueError) as exc:
            return AdapterTestResult(
                adapter=self.name,
                display_name=self.display_name,
                status="INCOMPLETE",
                checks=(CheckResult("Probe session", "INCOMPLETE", f"Codex could not complete the probe suite: {exc}"),),
                adapter_version=status.version,
            )


__all__ = ["CodexCLIAdapter"]
