from __future__ import annotations

import secrets
import socket
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from ..models import TraceValidationError
from ..validation import strict_json_loads

_MAX_REQUEST_BYTES = 5_000_000
_MAX_PAYLOADS = 100
_MAX_TOTAL_BYTES = 16_000_000


@dataclass(frozen=True)
class ToolDecision:
    tool_use_id: str
    tool_name: str | None
    decision: str
    source: str | None
    session_id: str | None = None


def _otel_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for key in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
        if key in value:
            return value[key]
    return None


def _objects(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TraceValidationError(f"OTLP {field} must be an array of objects")
    return value


def _attributes(record: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in _objects(record.get("attributes", []), "attributes"):
        key = item.get("key")
        if not isinstance(key, str) or key in result:
            raise TraceValidationError("OTLP attribute keys are missing or duplicated")
        result[key] = _otel_value(item.get("value"))
    return result


def extract_tool_decisions(payloads: list[dict[str, Any]]) -> list[ToolDecision]:
    decisions: list[ToolDecision] = []
    seen: set[ToolDecision] = set()
    if not isinstance(payloads, list) or len(payloads) > _MAX_PAYLOADS:
        raise TraceValidationError("OTLP payload count is invalid")
    for payload in payloads:
        if not isinstance(payload, dict):
            raise TraceValidationError("OTLP payload must be an object")
        for resource in _objects(payload.get("resourceLogs", []), "resourceLogs"):
            for scope in _objects(resource.get("scopeLogs", []), "scopeLogs"):
                for record in _objects(scope.get("logRecords", []), "logRecords"):
                    attrs = _attributes(record)
                    event_name = attrs.get("event.name") or _otel_value(record.get("body"))
                    if not isinstance(event_name, str) or event_name not in {
                        "tool_decision",
                        "claude_code.tool_decision",
                    }:
                        continue
                    uid = attrs.get("tool_use_id")
                    decision = attrs.get("decision") or attrs.get("decision_type")
                    if (
                        not isinstance(uid, str)
                        or not uid
                        or not isinstance(decision, str)
                        or decision not in {"accept", "reject", "cancelled"}
                    ):
                        raise TraceValidationError("OTLP tool decision has invalid identifier or decision")
                    name = attrs.get("tool_name")
                    source = attrs.get("source") or attrs.get("decision_source")
                    session = attrs.get("session.id")
                    for value in (name, source, session):
                        if value is not None and not isinstance(value, str):
                            raise TraceValidationError("OTLP decision correlation fields must be strings")
                    item = ToolDecision(uid, name, decision, source, session)
                    if item not in seen:
                        seen.add(item)
                        decisions.append(item)
    return decisions


class LocalOtelCollector:
    """Bounded loopback-only OTLP JSON receiver for one explicit live test."""

    def __init__(self) -> None:
        self._payloads: list[dict[str, Any]] = []
        self._errors: list[str] = []
        self._bytes = 0
        self._lock = threading.Lock()
        self._path = f"/{secrets.token_urlsafe(18)}/v1/logs"
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self) -> None:
                super().setup()
                self.connection.settimeout(3)

            def do_POST(self) -> None:  # noqa: N802
                if self.path != outer._path:
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= _MAX_REQUEST_BYTES:
                        raise ValueError("telemetry request size is invalid")
                    with outer._lock:
                        if outer._bytes + length > _MAX_TOTAL_BYTES or len(outer._payloads) >= _MAX_PAYLOADS:
                            raise ValueError("telemetry capture limit reached")
                        outer._bytes += length
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        raise ValueError("telemetry request was truncated")
                    payload = strict_json_loads(raw, max_bytes=_MAX_REQUEST_BYTES)
                    if not isinstance(payload, dict):
                        raise ValueError("telemetry payload must be an object")
                    with outer._lock:
                        if len(outer._payloads) >= _MAX_PAYLOADS:
                            raise ValueError("telemetry payload limit reached")
                        outer._payloads.append(payload)
                except (ValueError, OSError, socket.timeout) as exc:
                    with outer._lock:
                        if len(outer._errors) < 10:
                            outer._errors.append(str(exc))
                    self.send_response(400)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, format: str, *args: Any) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, name="agentack-otel", daemon=True)

    @property
    def endpoint(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}{self._path}"

    def __enter__(self) -> "LocalOtelCollector":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def payloads(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._payloads)

    def errors(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._errors)
