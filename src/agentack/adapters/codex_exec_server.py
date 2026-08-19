from __future__ import annotations

import socket
import subprocess
import time
from collections import deque
from pathlib import Path


class LocalCodexExecServerError(RuntimeError):
    pass


class LocalCodexExecServer:
    """Run Codex's own exec-server on a short-lived loopback websocket.

    AgentAck does not implement the execution protocol. The installed Codex
    binary owns the environment and command execution path; AgentAck only starts
    it locally and gives App Server its loopback URL.
    """

    def __init__(self, executable: str, *, cwd: Path) -> None:
        self.executable = executable
        self.cwd = cwd
        self._process: subprocess.Popen[str] | None = None
        self._stderr: deque[str] = deque(maxlen=30)
        self._port: int | None = None

    @property
    def url(self) -> str:
        if self._port is None:
            raise LocalCodexExecServerError("Codex exec-server is not running")
        return f"ws://127.0.0.1:{self._port}"

    @staticmethod
    def _reserve_port() -> int:
        # The socket is closed immediately before Codex binds it. This is a
        # narrow loopback-only race; failure to bind is detected fail-closed.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _last_error(self) -> str:
        if self._process is not None and self._process.stderr is not None:
            try:
                while True:
                    line = self._process.stderr.readline()
                    if not line:
                        break
                    text = line.strip()
                    if text:
                        self._stderr.append(text)
            except OSError:
                pass
        return self._stderr[-1] if self._stderr else "process exited"

    def __enter__(self) -> "LocalCodexExecServer":
        self._port = self._reserve_port()
        self._process = subprocess.Popen(
            [self.executable, "exec-server", "--listen", self.url],
            cwd=self.cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise LocalCodexExecServerError(f"Codex exec-server exited before readiness: {self._last_error()}")
            try:
                with socket.create_connection(("127.0.0.1", self._port), timeout=0.2):
                    return self
            except OSError:
                time.sleep(0.05)
        raise LocalCodexExecServerError("timed out waiting for Codex exec-server loopback readiness")

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stderr is not None:
            process.stderr.close()


__all__ = ["LocalCodexExecServer", "LocalCodexExecServerError"]
