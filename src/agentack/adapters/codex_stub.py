from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

MAX_REQUEST_BYTES = 2 * 1024 * 1024


def _usage() -> dict[str, Any]:
    return {
        "input_tokens": 0,
        "input_tokens_details": None,
        "output_tokens": 0,
        "output_tokens_details": None,
        "total_tokens": 0,
    }


def _sse(events: Sequence[dict[str, Any]]) -> bytes:
    chunks: list[str] = []
    for event in events:
        event_type = str(event["type"])
        chunks.append(f"event: {event_type}\n")
        if len(event) > 1:
            chunks.append("data: " + json.dumps(event, separators=(",", ":")) + "\n\n")
        else:
            chunks.append("data: {}\n\n")
    return "".join(chunks).encode("utf-8")


def _function_call_events(index: int, command: str) -> bytes:
    response_id = f"agentack-response-{index}"
    call_id = f"agentack-shell-{index}"
    arguments = json.dumps({"command": command}, separators=(",", ":"))
    return _sse(
        [
            {"type": "response.created", "response": {"id": response_id}},
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": "shell_command",
                    "arguments": arguments,
                },
            },
            {"type": "response.completed", "response": {"id": response_id, "usage": _usage()}},
        ]
    )


def _completion_events(index: int) -> bytes:
    response_id = f"agentack-completion-{index}"
    return _sse(
        [
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "message",
                    "role": "assistant",
                    "id": f"agentack-message-{index}",
                    "content": [{"type": "output_text", "text": "done"}],
                },
            },
            {"type": "response.completed", "response": {"id": response_id, "usage": _usage()}},
        ]
    )


def _has_tool_output(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    items = payload.get("input")
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"function_call_output", "custom_tool_call_output"}:
            return True
    return False


class DeterministicCodexProvider:
    """Loopback-only Responses API stub that deterministically requests safe shell calls.

    The stub chooses only the synthetic action. The installed Codex binary still
    constructs the command item, requests approval, enforces the decision, and
    executes or blocks the command.
    """

    def __init__(self, commands: Sequence[str]) -> None:
        self._commands = tuple(commands)
        self._lock = threading.Lock()
        self._next_command = 0
        self._completion_count = 0
        self._error: str | None = None
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("deterministic Codex provider is not running")
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}/v1"

    @property
    def requests_started(self) -> int:
        with self._lock:
            return self._next_command

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def _record_error(self, detail: str) -> None:
        with self._lock:
            if self._error is None:
                self._error = detail

    def _next_response(self, payload: Any) -> tuple[int, bytes, str]:
        if _has_tool_output(payload):
            with self._lock:
                self._completion_count += 1
                index = self._completion_count
            return 200, _completion_events(index), "text/event-stream"

        with self._lock:
            if self._next_command >= len(self._commands):
                self._error = "Codex requested more model turns than the five deterministic AgentAck probes"
                body = json.dumps({"error": {"message": self._error}}).encode("utf-8")
                return 409, body, "application/json"
            self._next_command += 1
            index = self._next_command
            command = self._commands[index - 1]
        return 200, _function_call_events(index, command), "text/event-stream"

    def __enter__(self) -> "DeterministicCodexProvider":
        provider = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AgentAckCodexStub/1"

            def log_message(self, _format: str, *_args: Any) -> None:
                return

            def do_POST(self) -> None:  # noqa: N802
                if self.path.split("?", 1)[0] != "/v1/responses":
                    self.send_error(404)
                    return
                encoding = self.headers.get("Content-Encoding", "").strip().lower()
                if encoding not in {"", "identity"}:
                    provider._record_error(f"Codex sent unsupported compressed loopback evidence: {encoding}")
                    self.send_error(415)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self.send_error(400)
                    return
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    provider._record_error("Codex loopback model request was empty or exceeded the bounded request size")
                    self.send_error(413 if length > MAX_REQUEST_BYTES else 400)
                    return
                try:
                    raw = self.rfile.read(length)
                    payload = json.loads(raw)
                except (OSError, UnicodeError, json.JSONDecodeError):
                    provider._record_error("Codex loopback model request was not valid bounded JSON")
                    self.send_error(400)
                    return
                status, body, content_type = provider._next_response(payload)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="agentack-codex-model", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def write_codex_probe_config(codex_home: Path, *, provider_base_url: str) -> None:
    """Write an isolated Codex config following Codex's own mock-provider test pattern."""
    codex_home.mkdir(parents=True, exist_ok=True)
    config = f'''model = "mock-model"
model_provider = "agentack_local"
approval_policy = "untrusted"
sandbox_mode = "workspace-write"

[model_providers.agentack_local]
name = "AgentAck deterministic local probe"
base_url = "{provider_base_url}"
wire_api = "responses"
request_max_retries = 0
stream_max_retries = 0
requires_openai_auth = false
supports_websockets = false
'''
    (codex_home / "config.toml").write_text(config, encoding="utf-8")


__all__ = ["DeterministicCodexProvider", "write_codex_probe_config"]
